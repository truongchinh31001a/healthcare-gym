"""Research-only fusion estimates with checkpoint-bound intervals and novelty flags."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.multimodal.inference import estimate_pair


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--side", type=Path, required=True)
    parser.add_argument("--height-cm", type=float, required=True)
    parser.add_argument("--weight-kg", type=float, required=True)
    parser.add_argument("--gender", choices=("male", "female"), required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    model_dir = ROOT / "models/bodym_phase3"
    quality = json.loads((ROOT / "configs/bodym_phase2.json").read_text())["quality"]
    result = estimate_pair(model_dir / "fusion/model.pt", model_dir / "fusion/calibration.json", model_dir / "novelty.json",
                           args.front, args.side, args.height_cm, args.weight_kg, args.gender, quality, args.device)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
