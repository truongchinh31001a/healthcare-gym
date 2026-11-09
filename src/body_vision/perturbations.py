"""Synthetic raw-mask stress tests, preserving source files and target labels."""
import numpy as np
from PIL import Image
from scipy import ndimage

TRANSFORMS = ("identity", "translate", "erode_2px", "dilate_2px", "rotate_5deg", "remove_top_10pct")


def perturb(mask, name):
    mask = np.asarray(mask, dtype=np.uint8)
    if mask.ndim != 2 or name not in TRANSFORMS:
        raise ValueError("Expected 2D mask and a known stress-test transform")
    result = mask.copy()
    active = mask > 127
    if not active.any():
        raise ValueError("Cannot perturb an empty mask")
    yy, xx = np.nonzero(active)
    if name == "translate":
        # Pad instead of wrapping or clipping. Canonical bbox cropping should cancel translation.
        result = np.pad(result, ((13, 31), (19, 37)))
    elif name == "erode_2px":
        result = ndimage.binary_erosion(active, iterations=2).astype(np.uint8) * 255
    elif name == "dilate_2px":
        result = ndimage.binary_dilation(active, iterations=2).astype(np.uint8) * 255
    elif name == "rotate_5deg":
        result = np.asarray(Image.fromarray(result).rotate(5, resample=Image.Resampling.NEAREST, expand=True, fillcolor=0))
    elif name == "remove_top_10pct":
        result[:int(yy.min() + 0.1 * (yy.max() - yy.min() + 1))] = 0
    return result
