"""Predict body measurements using the project's selected default CNN."""

import json
from pathlib import Path

from predict_bodym_cnn import main as predict_cnn


def main():
    root = Path(__file__).resolve().parents[1]
    selected = json.loads((root / "configs/default_model.json").read_text(encoding="utf-8"))
    if selected["model_type"] != "two_view_cnn_metadata":
        raise ValueError(f"Unsupported default model: {selected['model_type']}")
    predict_cnn(default_checkpoint=root / selected["checkpoint"])


if __name__ == "__main__":
    main()
