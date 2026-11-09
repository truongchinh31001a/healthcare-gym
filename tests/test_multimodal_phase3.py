"""Phase 3 tests for actual branch removal, leakage and subject-level intervals."""
import unittest
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np
import torch

from scripts.run_bodym_phase3 import make_split, validate_phase3_split
from src.multimodal.model import AblationModel
from src.multimodal.calibration import finite_sample_quantile, fit_calibrator, interval_metrics, subject_max_errors
from src.multimodal.ood import fit_novelty, novelty_flags, novelty_features, FEATURE_NAMES
from src.multimodal.inference import load_bundle
from scripts.bodym_cnn import TARGETS, METADATA, PREPROCESS_VERSION


class Phase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)
        cls.config = {"channels": [4, 8], "metadata_hidden": [8, 4], "fusion_hidden": [16], "dropout": 0.0}

    def test_ablation_really_removes_unused_branches(self):
        images, metadata = torch.rand(4, 2, 1, 32, 24), torch.randn(4, 3)
        for variant in ("tabular_only", "image_only", "fusion"):
            torch.manual_seed(42)
            model = AblationModel(self.config, variant).eval()
            baseline = model(images, metadata)
            self.assertEqual(baseline.shape, (4, 3))
            if variant == "tabular_only":
                self.assertIsNone(model.encoder)
                torch.testing.assert_close(model(images + 1, metadata), baseline, rtol=0, atol=0)
            elif variant == "image_only":
                self.assertIsNone(model.metadata_encoder)
                torch.testing.assert_close(model(images, metadata + 10), baseline, rtol=0, atol=0)
            else:
                img = images.clone().requires_grad_()
                known = metadata.clone().requires_grad_()
                model(img, known).square().sum().backward()
                self.assertGreater(img.grad.abs().sum().item(), 0)
                self.assertGreater(known.grad.abs().sum().item(), 0)

    def test_split_is_reproducible_and_subject_disjoint(self):
        original = {"fit_subject_ids": [f"p{i}" for i in range(20)], "validation_subject_ids": ["v1", "v2"]}
        split = make_split(original, 42, .2)
        self.assertEqual(split, make_split(original, 42, .2))
        self.assertEqual(len(split["calibration_subject_ids"]), 4)
        split["proper_fit_subject_ids"].append(split["calibration_subject_ids"][0])
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_phase3_split(split, original["fit_subject_ids"] + original["validation_subject_ids"])

    def test_finite_sample_quantile_uses_n_plus_one(self):
        radius, rank = finite_sample_quantile(np.arange(1, 101), .1)
        self.assertEqual(rank, 91)
        self.assertEqual(radius, 91)
        with self.assertRaises(ValueError):
            finite_sample_quantile(np.arange(5), .1)
        for bad in (np.array([np.nan]), np.array([-1])):
            with self.assertRaises(ValueError):
                finite_sample_quantile(bad, .5)

    def test_calibration_collapses_to_worst_photo_per_person(self):
        ids = np.repeat([f"p{i}" for i in range(10)], 2)
        y = np.zeros((20, 3))
        pred = np.arange(20)[:, None] * np.ones((1, 3))
        maxima = subject_max_errors(y, pred, ids)
        np.testing.assert_array_equal(maxima[:, 0], np.arange(1, 20, 2))
        cal = fit_calibrator(y, pred, ids, alpha=.1, trained_ids=["train"], tuned_ids=["tune"], checkpoint_sha256="abc")
        self.assertEqual(cal["calibration_subjects"], 10)
        self.assertEqual(cal["joint_radius_cm"], 19)
        # Replicating a photo cannot change its subject maximum.
        repeat = np.r_[np.arange(20), [0] * 50]
        other = fit_calibrator(y[repeat], pred[repeat], ids[repeat], alpha=.1,
                              trained_ids=["train"], tuned_ids=["tune"], checkpoint_sha256="abc")
        self.assertEqual(cal, other)

    def test_calibration_rejects_both_training_and_selection_leakage(self):
        for trained, tuned in ((["p0"], []), ([], ["p0"])):
            with self.assertRaisesRegex(ValueError, "overlap"):
                fit_calibrator(np.zeros((10, 3)), np.ones((10, 3)), [f"p{i}" for i in range(10)],
                               alpha=.1, trained_ids=trained, tuned_ids=tuned, checkpoint_sha256="abc")

    def test_subject_coverage_is_not_photo_coverage(self):
        y = np.zeros((3, 3))
        pred = np.array([[.5] * 3, [3] * 3, [1] * 3])
        cal = {"per_target_radius_cm": {key: 2 for key in ("chest", "waist", "hip")},
               "joint_radius_cm": 2, "nominal_coverage": .9}
        result = interval_metrics(y, pred, np.array(["a", "a", "b"]), cal)
        self.assertEqual(result["per_target_subject_all_photos_coverage"]["chest"], .5)
        self.assertEqual(result["per_target_subject_balanced_pair_coverage"]["chest"], .75)
        self.assertEqual(result["joint_subject_all_targets_all_photos_coverage"], .5)

    def test_joint_radius_and_per_target_width_are_separate(self):
        ids = np.array([f"p{i}" for i in range(10)])
        pred = np.tile([1, 2, 3], (10, 1))
        cal = fit_calibrator(np.zeros((10, 3)), pred, ids, alpha=.1,
                             trained_ids=[], tuned_ids=[], checkpoint_sha256="abc")
        self.assertEqual(cal["per_target_radius_cm"], {"chest": 1, "waist": 2, "hip": 3})
        self.assertEqual(cal["joint_radius_cm"], 3)

    def test_novelty_is_train_only_and_does_not_fit_on_test(self):
        features = np.ones((20, len(FEATURE_NAMES)))
        features[:, 0] = np.arange(150, 170)
        features[:, 1] = np.arange(50, 70)
        ids = np.array([str(i) for i in range(20)])
        detector = fit_novelty(features, ids)
        before = dict(detector)
        heldout = features[:1].copy()
        heldout[0, :2] = [250, 200]
        flags = novelty_flags(heldout, detector)
        self.assertTrue(flags["flagged"][0])
        self.assertTrue(flags["metadata_range_flag"][0])
        self.assertEqual(detector, before)
        repeated = np.r_[np.arange(20), [0] * 100]
        self.assertEqual(detector, fit_novelty(features[repeated], ids[repeated]))

    def test_novelty_features_reject_empty_or_nonbinary_inputs(self):
        images = np.zeros((2, 2, 1, 32, 24), dtype=np.uint8)
        images[:, :, :, 4:28, 8:16] = 1
        known = np.array([[170, 70, 1], [160, 60, 0]])
        self.assertEqual(novelty_features(images, known).shape, (2, len(FEATURE_NAMES)))
        with self.assertRaises(ValueError):
            novelty_features(images * 255, known)
        with self.assertRaises(ValueError):
            novelty_features(np.zeros_like(images), known)

    def test_bundle_rejects_mismatched_checkpoint_and_split(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = AblationModel(self.config, "fusion")
            path = root / "model.pt"
            torch.save({"phase": "refit_without_calibration", "preprocess_version": PREPROCESS_VERSION,
                        "config": self.config, "variant": "fusion", "targets": list(TARGETS),
                        "metadata_names": list(METADATA), "split_sha256": "split-a", "state_dict": model.state_dict()}, path)
            cal_path, detector_path = root / "calibration.json", root / "novelty.json"
            calibrator = {"checkpoint_sha256": "wrong", "split_sha256": "split-a", "targets": list(TARGETS)}
            cal_path.write_text(json.dumps(calibrator))
            detector_path.write_text(json.dumps({"preprocessing_version": PREPROCESS_VERSION, "split_sha256": "split-a"}))
            with self.assertRaisesRegex(ValueError, "different checkpoint"):
                load_bundle(path, cal_path, detector_path)
            calibrator["checkpoint_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            calibrator["split_sha256"] = "split-b"
            cal_path.write_text(json.dumps(calibrator))
            with self.assertRaisesRegex(ValueError, "different splits"):
                load_bundle(path, cal_path, detector_path)
            calibrator["split_sha256"] = "split-a"
            cal_path.write_text(json.dumps(calibrator))
            loaded, _, _, _ = load_bundle(path, cal_path, detector_path)
            self.assertEqual(loaded.variant, "fusion")


if __name__ == "__main__":
    unittest.main()
