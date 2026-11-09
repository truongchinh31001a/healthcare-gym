"""Train the project's default two-view CNN."""

import json
from pathlib import Path

from run_bodym_cnn import main as train_cnn


def main():
    root = Path(__file__).resolve().parents[1]
    selected = json.loads((root / "configs/default_model.json").read_text(encoding="utf-8"))
    if selected["model_type"] != "two_view_cnn_metadata":
        raise ValueError(f"Unsupported default model: {selected['model_type']}")
    train_cnn(default_config=root / selected["training_config"],
              default_subject_split=root / selected["subject_split"])


if __name__ == "__main__":
    main()
