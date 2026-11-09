"""Research inference: a point model and only its own calibrator/novelty artifact."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import torch

from scripts.bodym_cnn import preprocess_silhouette, TARGETS, PREPROCESS_VERSION
from src.body_vision.quality import assess_mask
from .model import load_ablation
from .ood import novelty_features, novelty_flags


def load_bundle(checkpoint_path, calibration_path, novelty_path, device="cpu"):
    model_sha = hashlib.sha256(Path(checkpoint_path).read_bytes()).hexdigest()
    calibrator = json.loads(Path(calibration_path).read_text(encoding="utf-8"))
    if calibrator["checkpoint_sha256"] != model_sha:
        raise ValueError("Calibrator belongs to a different checkpoint")
    model, checkpoint = load_ablation(checkpoint_path, device)
    detector = json.loads(Path(novelty_path).read_text(encoding="utf-8"))
    if detector["preprocessing_version"] != PREPROCESS_VERSION or calibrator["targets"] != list(TARGETS):
        raise ValueError("Bundle schema/preprocessing mismatch")
    if calibrator["split_sha256"] != checkpoint["split_sha256"] or detector["split_sha256"] != checkpoint["split_sha256"]:
        raise ValueError("Bundle artifacts belong to different splits")
    return model, checkpoint, calibrator, detector


@torch.inference_mode()
def estimate_pair(checkpoint_path, calibration_path, novelty_path, front, side,
                  height_cm, weight_kg, gender, quality_config, device="cpu"):
    if gender not in ("male", "female") or not np.isfinite([height_cm, weight_kg]).all() or min(height_cm, weight_kg) <= 0:
        raise ValueError("Expected positive finite height/weight and supplied dataset-compatible gender label")
    model, checkpoint, cal, detector = load_bundle(checkpoint_path, calibration_path, novelty_path, device)
    quality = {}
    for view, path in (("front", front), ("side", side)):
        with Image.open(path) as image:
            if image.mode not in ("1", "L", "P"):
                raise ValueError("Only presegmented grayscale silhouettes supported; RGB inference not validated")
            quality[view] = assess_mask(np.asarray(image.convert("L")), quality_config)
        if not quality[view]["usable"]:
            raise ValueError(f"Unusable {view} silhouette: {quality[view]['flags']}")
    images = np.stack([preprocess_silhouette(path, checkpoint["config"]) for path in (front, side)])[None]
    metadata = np.array([[height_cm, weight_kg, float(gender == "male")]], dtype=np.float32)
    normalization = checkpoint["normalization"]
    known = (metadata - normalization["metadata_mean"]) / normalization["metadata_std"]
    raw = model(torch.tensor(images, dtype=torch.float32, device=device), torch.tensor(known, dtype=torch.float32, device=device))
    prediction = raw.cpu().numpy()[0] * normalization["target_std"] + normalization["target_mean"]
    flags = novelty_flags(novelty_features(images, metadata), detector)
    estimates = {}
    for key, value in zip(TARGETS, prediction):
        radius = cal["per_target_radius_cm"][key]
        estimates[key] = {"point_cm": float(value), "per_target_interval_cm": [float(value - radius), float(value + radius)],
                          "joint_interval_cm": [float(value - cal["joint_radius_cm"]), float(value + cal["joint_radius_cm"])]}
    needs_review = bool(flags["flagged"][0]) or any(value["flags"] for value in quality.values())
    return {"research_only": True, "provenance": "inferred", "verification_status": "unverified_estimate",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "variant": checkpoint["variant"],
            "checkpoint_sha256": cal["checkpoint_sha256"], "nominal_coverage": cal["nominal_coverage"],
            "coverage_scope": cal["coverage_unit"], "uncertainty_limitation": cal["limitations"],
            "quality_flags": {key: value["flags"] for key, value in quality.items()},
            "ood": {"flagged": bool(flags["flagged"][0]), "distance": float(flags["distance"][0]),
                    "threshold": detector["threshold"], "metadata_range_flag": bool(flags["metadata_range_flag"][0]),
                    "method": detector["method"], "limitations": detector["limitations"]},
            "requires_review": True, "input_quality_requires_review": needs_review, "estimates": estimates}
