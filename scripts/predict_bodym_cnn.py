"""Predict chest, waist and hip in cm from an actual pair of silhouettes."""

import argparse
import json
from pathlib import Path

from bodym_cnn import ROOT, predict_pair


def main(default_checkpoint=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--side", type=Path, required=True)
    parser.add_argument("--height-cm", type=float, required=True)
    parser.add_argument("--weight-kg", type=float, required=True)
    parser.add_argument("--gender", choices=("male", "female"), required=True)
    parser.add_argument("--checkpoint", type=Path, default=default_checkpoint or ROOT / "models/bodym_cnn/model.pt")
    args = parser.parse_args()
    prediction = predict_pair(args.checkpoint, args.front, args.side, args.height_cm, args.weight_kg, args.gender)
    print(json.dumps({"units": "cm", "predictions": prediction}, indent=2))


if __name__ == "__main__":
    main()
