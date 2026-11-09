"""Shared two-view CNN, preprocessing and inference for BodyM."""

from pathlib import Path

import numpy as np
from PIL import Image
import torch
from torch import nn


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("chest", "waist", "hip")
METADATA = ("height_cm", "weight_kg", "male")
VIEWS = ("mask", "mask_left")
PREPROCESS_VERSION = "binary-bbox-letterbox-v1"


class TwoViewBodyCNN(nn.Module):
    """One shared CNN for both images, with a metadata branch and fusion MLP."""

    def __init__(self, config):
        super().__init__()
        layers = []
        previous = 1
        for channels in config["channels"]:
            layers.extend([
                nn.Conv2d(previous, channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(channels), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            ])
            previous = channels
        self.encoder = nn.Sequential(*layers, nn.AdaptiveAvgPool2d(1), nn.Flatten())
        metadata_layers = []
        previous = len(METADATA)
        for width in config["metadata_hidden"]:
            metadata_layers.extend([nn.Linear(previous, width), nn.ReLU(inplace=True)])
            previous = width
        self.metadata_encoder = nn.Sequential(*metadata_layers)
        previous = 2 * config["channels"][-1] + previous
        head = []
        for width in config["fusion_hidden"]:
            head.extend([nn.Linear(previous, width), nn.ReLU(inplace=True), nn.Dropout(config["dropout"])])
            previous = width
        head.append(nn.Linear(previous, len(TARGETS)))
        self.head = nn.Sequential(*head)

    def forward(self, images, metadata):
        # Stack views into the batch so BatchNorm sees both views together.
        # images: [B, 2, 1, H, W]; encoder weights are shared by construction.
        batch = images.shape[0]
        shape = self.encoder(images.reshape(batch * 2, *images.shape[2:]))
        shape = shape.reshape(batch, -1)
        return self.head(torch.cat([shape, self.metadata_encoder(metadata)], dim=1))


def preprocess_silhouette(path, config):
    height, width = config["image_height"], config["image_width"]
    padding = config["padding"]
    if height <= padding * 2 or width <= padding * 2:
        raise ValueError("Image size must exceed twice the padding")
    with Image.open(path) as image:
        binary = image.convert("L").point(lambda pixel: 255 if pixel > 127 else 0)
        bbox = binary.getbbox()
        if bbox is None:
            raise ValueError(f"Empty silhouette: {path}")
        body = binary.crop(bbox)
        scale = min((height - 2 * padding) / body.height, (width - 2 * padding) / body.width)
        resized = body.resize((max(1, round(body.width * scale)), max(1, round(body.height * scale))), Image.Resampling.NEAREST)
        canvas = Image.new("L", (width, height), 0)
        canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
        return (np.asarray(canvas) > 127).astype(np.uint8)[None]


def fit_normalization(metadata, targets, subject_ids):
    """Fit on one row per training subject, never on validation/test rows."""
    _, indices = np.unique(subject_ids, return_index=True)
    return {
        "metadata_mean": metadata[indices].mean(axis=0).tolist(),
        "metadata_std": np.maximum(metadata[indices].std(axis=0), 1e-6).tolist(),
        "target_mean": targets[indices].mean(axis=0).tolist(),
        "target_std": np.maximum(targets[indices].std(axis=0), 1e-6).tolist(),
    }


@torch.no_grad()
def calibrate_batchnorm(model, images, batch_size):
    """Estimate encoder BN statistics from training images at fixed weights.

    Dropout stays off. No labels, validation images or optimizer steps are used.
    This reduces sensitivity to the final few shuffled mini-batches and aligns
    the statistics with the FP32 evaluation path after mixed-precision training.
    """
    layers = [layer for layer in model.encoder.modules() if isinstance(layer, nn.BatchNorm2d)]
    momenta = [layer.momentum for layer in layers]
    model.eval()
    for layer in layers:
        layer.reset_running_stats()
        layer.momentum = None
        layer.train()
    try:
        for start in range(0, len(images), batch_size):
            batch = images[start:start + batch_size].float()
            model.encoder(batch.reshape(-1, *batch.shape[2:]))
    finally:
        for layer, momentum in zip(layers, momenta):
            layer.momentum = momentum
        model.eval()


def load_model(checkpoint_path, device="cpu"):
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    if tuple(checkpoint["targets"]) != TARGETS:
        raise ValueError("Checkpoint target schema mismatch")
    model = TwoViewBodyCNN(checkpoint["config"]).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model, checkpoint


@torch.inference_mode()
def predict_pair(checkpoint_path, front_path, side_path, height_cm, weight_kg, gender, device="cpu"):
    if not np.isfinite([height_cm, weight_kg]).all() or height_cm <= 0 or weight_kg <= 0 or gender not in ("male", "female"):
        raise ValueError("Positive height/weight and gender male/female are required")
    model, checkpoint = load_model(checkpoint_path, device)
    config, normalization = checkpoint["config"], checkpoint["normalization"]
    images = np.stack([preprocess_silhouette(path, config) for path in (front_path, side_path)])
    metadata = np.array([[height_cm, weight_kg, float(gender == "male")]], dtype=np.float32)
    metadata = (metadata - normalization["metadata_mean"]) / normalization["metadata_std"]
    output = model(torch.tensor(images[None], dtype=torch.float32, device=device),
                   torch.tensor(metadata, dtype=torch.float32, device=device))
    result = output.cpu().numpy()[0] * normalization["target_std"] + normalization["target_mean"]
    return dict(zip(TARGETS, map(float, result)))
