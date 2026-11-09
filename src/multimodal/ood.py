"""Training-only robust-distance novelty heuristic, not a calibrated OOD classifier."""
import numpy as np

FEATURE_NAMES = ["height_cm", "weight_kg", "provided_male"] + [f"{view}_{key}" for view in ("front", "side")
    for key in ("bbox_aspect", "fill", "span_10", "span_25", "span_40", "span_55", "span_70", "span_85")]


def novelty_features(images, metadata):
    images, metadata = np.asarray(images), np.asarray(metadata)
    if images.ndim != 5 or images.shape[1:3] != (2, 1) or metadata.shape != (len(images), 3):
        raise ValueError("Expected [N,2,1,H,W] binary masks and [N,3] metadata")
    if not np.isfinite(metadata).all() or not np.isin(images, [0, 1]).all():
        raise ValueError("Novelty features require finite metadata and binary masks")
    result = []
    for pair, known in zip(images, metadata):
        row = list(known)
        for view in pair[:, 0]:
            yy, xx = np.nonzero(view)
            if not len(xx):
                raise ValueError("Empty silhouette")
            crop = view[yy.min():yy.max() + 1, xx.min():xx.max() + 1]
            height, width = crop.shape
            spans = []
            for fraction in (.10, .25, .40, .55, .70, .85):
                active = np.flatnonzero(crop[min(height - 1, int(fraction * height))])
                spans.append((active[-1] - active[0] + 1) / height if len(active) else 0)
            row += [width / height, float(crop.mean()), *spans]
        result.append(row)
    return np.asarray(result, dtype=float)


def fit_novelty(features, ids, quantile=.99):
    features, ids = np.asarray(features), np.asarray(ids)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES) or len(features) != len(ids) or not len(features):
        raise ValueError("Novelty feature/ID mismatch")
    if not np.isfinite(features).all() or not 0 < quantile < 1:
        raise ValueError("Finite features and quantile in (0,1) required")
    # A fixed first photo per training person prevents repeated-photo counts dominating fit.
    _, index = np.unique(ids, return_index=True)
    unique = features[index]
    center = np.median(unique, axis=0)
    q25, q75 = np.quantile(unique, [.25, .75], axis=0)
    scale = np.maximum(q75 - q25, 1e-3)
    distance = np.sqrt(np.mean(((unique - center) / scale) ** 2, axis=1))
    return {"method": "training-iqr-distance-v1", "feature_names": FEATURE_NAMES,
            "center": center.tolist(), "scale": scale.tolist(), "training_subjects": len(index),
            "threshold": float(np.quantile(distance, quantile, method="higher")), "training_quantile": quantile,
            "height_weight_min": unique[:, :2].min(axis=0).tolist(), "height_weight_max": unique[:, :2].max(axis=0).tolist(),
            "limitations": "Heuristic only: no labeled OOD set, no AUROC or guarantee. Can miss pose, RGB segmentation and domain errors."}


def novelty_flags(features, detector):
    features = np.asarray(features)
    if features.ndim != 2 or features.shape[1] != len(detector["feature_names"]) or not np.isfinite(features).all():
        raise ValueError("Novelty feature mismatch")
    distance = np.sqrt(np.mean(((features - detector["center"]) / detector["scale"]) ** 2, axis=1))
    outside = ((features[:, :2] < detector["height_weight_min"]) | (features[:, :2] > detector["height_weight_max"])).any(axis=1)
    return {"distance": distance, "distance_flag": distance > detector["threshold"], "metadata_range_flag": outside,
            "flagged": (distance > detector["threshold"]) | outside}
