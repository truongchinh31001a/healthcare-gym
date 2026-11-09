"""Subject-balanced metrics and training-derived descriptive subgroup bins."""
import numpy as np

TARGETS = ("chest", "waist", "hip")


def score(y, prediction, ids):
    y, prediction, ids = np.asarray(y), np.asarray(prediction), np.asarray(ids)
    if y.ndim != 2 or y.shape != prediction.shape or y.shape[1] != len(TARGETS) or len(ids) != len(y) or not len(y):
        raise ValueError("Expected aligned nonempty [N,3] targets/predictions and N subject IDs")
    if not np.isfinite(y).all() or not np.isfinite(prediction).all():
        raise ValueError("Metrics require finite inputs")
    subjects, inverse, counts = np.unique(ids, return_inverse=True, return_counts=True)
    weights = 1 / counts[inverse]
    error = prediction - y
    mae = np.average(np.abs(error), weights=weights, axis=0)
    return {"subjects": len(subjects), "photo_pairs": len(ids), "mean_mae_cm": float(mae.mean()),
            "mae_cm": dict(zip(TARGETS, map(float, mae))),
            "rmse_cm": dict(zip(TARGETS, map(float, np.sqrt(np.average(error ** 2, weights=weights, axis=0))))),
            "bias_cm": dict(zip(TARGETS, map(float, np.average(error, weights=weights, axis=0))))}


def fit_subgroup_bins(metadata, ids):
    """Caller must pass FIT rows only; repeated photos do not affect quantiles."""
    metadata, ids = np.asarray(metadata), np.asarray(ids)
    _, indices = np.unique(ids, return_index=True)
    unique = metadata[indices]
    bmi = unique[:, 1] / (unique[:, 0] / 100) ** 2
    return {"fit_subjects": len(indices), "bmi_quartile_edges": np.quantile(bmi, [0.25, 0.5, 0.75]).tolist(),
            "height_weight_min": unique[:, :2].min(axis=0).tolist(),
            "height_weight_max": unique[:, :2].max(axis=0).tolist()}


def subgroup_scores(y, prediction, ids, metadata, bins, min_subjects=20):
    metadata = np.asarray(metadata)
    bmi = metadata[:, 1] / (metadata[:, 0] / 100) ** 2
    quartile = np.searchsorted(bins["bmi_quartile_edges"], bmi, side="right")
    masks = {"provided_gender_female": metadata[:, 2] == 0, "provided_gender_male": metadata[:, 2] == 1}
    masks.update({f"fit_bmi_Q{i + 1}": quartile == i for i in range(4)})
    out_of_range = ((metadata[:, :2] < bins["height_weight_min"]) | (metadata[:, :2] > bins["height_weight_max"])).any(axis=1)
    masks["outside_fit_height_weight_range"] = out_of_range
    groups = {}
    for name, mask in masks.items():
        if mask.any():
            value = score(y[mask], prediction[mask], ids[mask])
            value["small_group"] = value["subjects"] < min_subjects
            groups[name] = value
        else:
            groups[name] = {"subjects": 0, "photo_pairs": 0, "mean_mae_cm": None, "small_group": True}
    return groups
