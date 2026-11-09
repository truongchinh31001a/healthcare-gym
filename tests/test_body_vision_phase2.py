"""Independent behavioral checks for quality, weighting and stress transforms."""
import io
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bodym_cnn import preprocess_silhouette
from run_bodym_baseline import FEATURE_NAMES, silhouette_features
from src.body_vision.quality import assess_mask
from src.body_vision.analysis import score, fit_subgroup_bins, subgroup_scores
from src.body_vision.perturbations import perturb


class Phase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "configs/bodym_phase2.json").read_text())
        cls.cnn = json.loads((ROOT / "configs/bodym_cnn.json").read_text())

    def mask(self):
        mask = np.zeros((240, 160), dtype=np.uint8)
        mask[20:220, 40:120] = 255
        return mask

    def test_empty_and_full_frame_not_usable(self):
        for mask, flag in ((np.zeros((80, 80)), "empty_mask"), (np.full((80, 80), 255), "full_frame_foreground")):
            value = assess_mask(mask, self.config["quality"])
            self.assertIn(flag, value["flags"])
            self.assertFalse(value["usable"])

    def test_fragmented_and_frame_touch_flag_without_modifying_source(self):
        mask = self.mask()
        mask[:10, :10] = 255
        mask[30:200, 125:155] = 255
        before = mask.copy()
        value = assess_mask(mask, self.config["quality"])
        self.assertIn("foreground_touches_frame", value["flags"])
        self.assertIn("fragmented_foreground", value["flags"])
        self.assertTrue(value["usable"])
        np.testing.assert_array_equal(before, mask)

    def test_no_pose_certification_and_rgb_is_rejected(self):
        result = assess_mask(self.mask(), self.config["quality"])
        self.assertEqual(result["status"], "passed_mask_checks")
        self.assertNotIn("pose", result)
        with self.assertRaises(ValueError):
            assess_mask(np.zeros((80, 80, 3)), self.config["quality"])

    def test_nonbinary_mask_flagged(self):
        mask = self.mask()
        mask[30:80, 45:80] = 200
        self.assertIn("nonbinary_input", assess_mask(mask, self.config["quality"])["flags"])

    def test_metrics_give_equal_weight_to_each_person(self):
        # A has four photos with 1 cm error, B one with 9 cm error: mean is 5, not 2.6.
        ids = np.array(["a", "a", "a", "a", "b"])
        y = np.zeros((5, 3))
        prediction = np.array([[1] * 3] * 4 + [[9] * 3])
        result = score(y, prediction, ids)
        self.assertEqual(result["mean_mae_cm"], 5)
        self.assertAlmostEqual(result["rmse_cm"]["chest"], np.sqrt(41))
        self.assertEqual(result["bias_cm"]["chest"], 5)
        with self.assertRaises(ValueError):
            score(y, np.full_like(y, np.nan), ids)

    def test_subgroup_edges_ignore_repeated_photos_and_use_fit_inputs_only(self):
        metadata = np.array([[160, 50, 0], [180, 80, 1], [170, 90, 0], [190, 95, 1]], dtype=float)
        ids = np.array(["a", "b", "c", "d"])
        bins = fit_subgroup_bins(metadata, ids)
        repeated = [0, 0, 0, 1, 2, 3]
        self.assertEqual(bins, fit_subgroup_bins(metadata[repeated], ids[repeated]))
        before = json.loads(json.dumps(bins))
        heldout = np.array([[250, 200, 1]], dtype=float)
        groups = subgroup_scores(np.ones((1, 3)), np.full((1, 3), 2), np.array(["test"]), heldout, bins)
        self.assertEqual(groups["outside_fit_height_weight_range"]["subjects"], 1)
        self.assertTrue(groups["provided_gender_male"]["small_group"])
        self.assertEqual(groups["provided_gender_female"]["subjects"], 0)
        self.assertEqual(bins, before)

    def test_translation_normalizes_identically_and_stress_does_not_wrap(self):
        mask = self.mask()
        before = mask.copy()
        normalized = []
        for transformed in (mask, perturb(mask, "translate")):
            buffer = io.BytesIO()
            Image.fromarray(transformed).save(buffer, format="PNG")
            buffer.seek(0)
            normalized.append(preprocess_silhouette(buffer, self.cnn))
        np.testing.assert_array_equal(*normalized)
        self.assertLess(np.count_nonzero(perturb(mask, "erode_2px")), np.count_nonzero(mask))
        self.assertGreater(np.count_nonzero(perturb(mask, "dilate_2px")), np.count_nonzero(mask))
        self.assertLess(np.count_nonzero(perturb(mask, "remove_top_10pct")), np.count_nonzero(mask))
        np.testing.assert_array_equal(mask, before)

    def test_geometric_features_use_shape_not_target_measurements(self):
        features = []
        for mask in (self.mask(), perturb(self.mask(), "translate")):
            buffer = io.BytesIO()
            Image.fromarray(mask).save(buffer, format="PNG")
            buffer.seek(0)
            features.append(silhouette_features(buffer))
        np.testing.assert_allclose(*features)
        self.assertEqual(features[0].shape, (195,))
        self.assertEqual(len(FEATURE_NAMES), 393)
        self.assertTrue(np.isfinite(features[0]).all())
        self.assertFalse(set(("chest", "waist", "hip")) & set(FEATURE_NAMES))


if __name__ == "__main__":
    unittest.main()
