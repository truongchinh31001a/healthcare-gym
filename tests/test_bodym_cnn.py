"""Tests for split leakage, view connectivity and preprocessing invariants."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bodym_cnn import TwoViewBodyCNN, calibrate_batchnorm, fit_normalization, preprocess_silhouette
from run_bodym_cnn import validate_splits


class BodyMCNNTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)
        cls.config = json.loads((ROOT / "configs/bodym_cnn.json").read_text())

    def test_letterbox_preserves_shape_under_translation_and_scale(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index, (canvas_size, rectangle) in enumerate([
                ((100, 200), (10, 20, 39, 79)),
                ((200, 400), (60, 100, 119, 219)),
            ]):
                image = Image.new("L", canvas_size)
                ImageDraw.Draw(image).rectangle(rectangle, fill=255)
                path = Path(temporary) / f"{index}.png"
                image.save(path)
                paths.append(path)
            first, second = [preprocess_silhouette(path, self.config) for path in paths]
            np.testing.assert_array_equal(first, second)
            self.assertEqual(first.shape, (1, 128, 96))
            self.assertEqual(set(np.unique(first)), {0, 1})

    def test_empty_silhouette_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.png"
            Image.new("L", (32, 64)).save(path)
            with self.assertRaisesRegex(ValueError, "Empty silhouette"):
                preprocess_silhouette(path, self.config)

    def test_both_views_and_metadata_contribute_to_gradient(self):
        torch.manual_seed(42)
        model = TwoViewBodyCNN(self.config).eval()
        images = torch.rand(2, 2, 1, 128, 96, requires_grad=True)
        metadata = torch.randn(2, 3, requires_grad=True)
        result = model(images, metadata)
        self.assertEqual(tuple(result.shape), (2, 3))
        result.square().sum().backward()
        for view in (0, 1):
            self.assertGreater(float(images.grad[:, view].abs().sum()), 0)
        self.assertGreater(float(metadata.grad.abs().sum()), 0)
        self.assertGreater(float(model.encoder[0].weight.grad.abs().sum()), 0)

    def test_repeated_photos_do_not_bias_normalization(self):
        metadata = np.array([[160, 50, 0], [180, 80, 1]], dtype=float)
        labels = np.array([[80, 70, 90], [100, 90, 110]], dtype=float)
        unique = fit_normalization(metadata, labels, np.array(["a", "b"]))
        indices = np.array([0, 0, 0, 0, 1])
        repeated = fit_normalization(metadata[indices], labels[indices], np.array(["a", "a", "a", "a", "b"]))
        self.assertEqual(unique, repeated)

    def test_batchnorm_calibration_does_not_change_learned_weights(self):
        model = TwoViewBodyCNN(self.config)
        before = {name: value.detach().clone() for name, value in model.named_parameters()}
        images = torch.randint(0, 2, (4, 2, 1, 128, 96), dtype=torch.uint8)
        calibrate_batchnorm(model, images, batch_size=2)
        for name, value in model.named_parameters():
            torch.testing.assert_close(before[name], value, rtol=0, atol=0)
        self.assertFalse(model.training)
        self.assertEqual(int(model.encoder[1].num_batches_tracked), 2)
        self.assertGreater(float(model.encoder[1].running_mean.abs().sum()), 0)

    def test_split_guard_detects_leakage(self):
        data = {
            "train": {"subject_ids": np.array(["a", "b"]), "photo_ids": np.array(["p1", "p2"])},
            "testA": {"subject_ids": np.array(["c"]), "photo_ids": np.array(["p3"])},
            "testB": {"subject_ids": np.array(["c"]), "photo_ids": np.array(["p4"])},
        }
        record = {"fit_subject_ids": ["a"], "validation_subject_ids": ["b"]}
        validate_splits(data, record)  # Shared subjects between the two tests are allowed.
        data["testA"]["subject_ids"] = np.array(["a"])
        with self.assertRaisesRegex(ValueError, "Training subjects overlap"):
            validate_splits(data, record)
        data["testA"]["subject_ids"] = np.array(["c"])
        data["testA"]["photo_ids"] = np.array(["p1"])
        with self.assertRaisesRegex(ValueError, "Photo IDs overlap"):
            validate_splits(data, record)


if __name__ == "__main__":
    unittest.main()
