"""Deterministic mask checks. Flags never certify anatomical pose/completeness."""
import numpy as np
from scipy import ndimage


def assess_mask(pixels, config):
    pixels = np.asarray(pixels)
    if pixels.ndim != 2 or min(pixels.shape) == 0:
        raise ValueError("Expected a nonempty 2D grayscale silhouette; RGB segmentation is not implemented")
    if not np.isfinite(pixels).all() or pixels.min() < 0 or pixels.max() > 255:
        raise ValueError("Expected finite grayscale values in [0,255]")
    mask = pixels > 127
    foreground = int(mask.sum())
    flags = []
    result = {"width": pixels.shape[1], "height": pixels.shape[0], "foreground_pixels": foreground,
              "foreground_fraction": foreground / pixels.size,
              "nonbinary_fraction": float(((pixels != 0) & (pixels != 255)).mean()),
              "bbox": None, "largest_component_fraction": None, "components": 0}
    if result["nonbinary_fraction"] > config["max_nonbinary_fraction"]:
        flags.append("nonbinary_input")
    if foreground == 0:
        flags.append("empty_mask")
    else:
        yy, xx = np.nonzero(mask)
        bbox = [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1]
        result["bbox"] = bbox
        if foreground == pixels.size:
            flags.append("full_frame_foreground")
        if bbox[3] - bbox[1] < config["min_foreground_height_px"] or foreground < config["min_foreground_pixels"]:
            flags.append("low_foreground_resolution")
        if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
            flags.append("foreground_touches_frame")
        labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
        sizes = np.bincount(labels.ravel())[1:]
        result.update(components=int(count), largest_component_fraction=float(sizes.max() / foreground))
        if result["largest_component_fraction"] < config["min_largest_component_fraction"]:
            flags.append("fragmented_foreground")
    result["flags"] = flags
    result["status"] = "requires_review" if flags else "passed_mask_checks"
    result["usable"] = not any(flag in flags for flag in ("empty_mask", "full_frame_foreground"))
    return result
