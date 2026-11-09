"""Subject-max split-conformal radii with finite-sample order statistics.

No training/selection occurs here. Guarantees require exchangeable subject
bundles and a pipeline fixed independently of calibration. Reused research data
and changing capture/photo-count distributions limit applicability in this repo.
"""
import math
import numpy as np

TARGETS = ("chest", "waist", "hip")


def finite_sample_quantile(scores, alpha):
    scores = np.asarray(scores, dtype=float)
    if scores.ndim not in (1, 2) or not len(scores) or not np.isfinite(scores).all() or (scores < 0).any():
        raise ValueError("Expected finite nonnegative scores, one row per calibration subject")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly between 0 and 1")
    rank = math.ceil((len(scores) + 1) * (1 - alpha))
    if rank > len(scores):
        raise ValueError("Too few subjects for a finite radius at the requested coverage")
    return np.sort(scores, axis=0)[rank - 1], rank


def subject_max_errors(y, prediction, ids):
    y, prediction, ids = np.asarray(y), np.asarray(prediction), np.asarray(ids)
    if y.ndim != 2 or y.shape != prediction.shape or y.shape[1] != 3 or len(ids) != len(y) or not len(y):
        raise ValueError("Expected aligned nonempty [N,3] arrays and subject IDs")
    if not np.isfinite(y).all() or not np.isfinite(prediction).all():
        raise ValueError("Nonfinite targets/predictions")
    subjects, inverse = np.unique(ids, return_inverse=True)
    errors = np.abs(prediction - y)
    maxima = np.zeros((len(subjects), 3))
    np.maximum.at(maxima, inverse, errors)
    return maxima


def fit_calibrator(y, prediction, ids, *, alpha, trained_ids, tuned_ids, checkpoint_sha256):
    calibration_ids = set(map(str, ids))
    if calibration_ids & (set(map(str, trained_ids)) | set(map(str, tuned_ids))):
        raise ValueError("Calibration subjects overlap training or model selection")
    maxima = subject_max_errors(y, prediction, ids)
    per_target, rank = finite_sample_quantile(maxima, alpha)
    joint, _ = finite_sample_quantile(maxima.max(axis=1), alpha)
    return {"method": "subject-max-split-conformal-v1", "alpha": alpha,
            "nominal_coverage": 1 - alpha, "calibration_subjects": len(maxima), "order_statistic_rank": rank,
            "targets": list(TARGETS), "unit": "cm", "checkpoint_sha256": checkpoint_sha256,
            "per_target_radius_cm": dict(zip(TARGETS, map(float, per_target))), "joint_radius_cm": float(joint),
            "coverage_unit": "New subject bundle, all supplied photos. Per-target marginal; joint radius covers all 3 targets together.",
            "limitations": "Exchangeability required; subject/photo-count/capture domain shift and historical dataset reuse can invalidate guarantees. Not an individual health confidence probability."}


def interval_metrics(y, prediction, ids, calibrator):
    y, prediction, ids = np.asarray(y), np.asarray(prediction), np.asarray(ids)
    maxima = subject_max_errors(y, prediction, ids)
    radius = np.array([calibrator["per_target_radius_cm"][key] for key in TARGETS])
    pair_hit = np.abs(prediction - y) <= radius
    _, inverse, counts = np.unique(ids, return_inverse=True, return_counts=True)
    weights = 1 / counts[inverse]
    return {"subjects": len(maxima), "photo_pairs": len(ids), "nominal_coverage": calibrator["nominal_coverage"],
            "per_target_subject_all_photos_coverage": dict(zip(TARGETS, map(float, (maxima <= radius).mean(axis=0)))),
            "per_target_subject_balanced_pair_coverage": dict(zip(TARGETS, map(float, np.average(pair_hit, weights=weights, axis=0)))),
            "per_target_width_cm": dict(zip(TARGETS, map(float, 2 * radius))),
            "joint_subject_all_targets_all_photos_coverage": float((maxima.max(axis=1) <= calibrator["joint_radius_cm"]).mean()),
            "joint_width_cm": 2 * calibrator["joint_radius_cm"]}
