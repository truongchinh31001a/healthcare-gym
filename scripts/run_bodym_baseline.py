"""Reproducible BodyM chest/waist/hip baseline with subject-disjoint validation."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import pickle
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import PIL
import sklearn
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("chest", "waist", "hip")
VIEWS = ("mask", "mask_left")
PROFILE_BINS = 64
METADATA_NAMES = ["height_cm", "weight_kg", "male"]
# View scalar features are appended immediately after the profiles for each view.
FEATURE_NAMES = METADATA_NAMES.copy()
for _view in VIEWS:
    FEATURE_NAMES.extend(
        f"{_view}_{kind}_{index:02d}"
        for kind in ("span", "occupied", "center")
        for index in range(PROFILE_BINS)
    )
    FEATURE_NAMES.extend(f"{_view}_{kind}" for kind in ("aspect_ratio", "area", "fill_ratio"))


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def silhouette_features(path):
    with Image.open(path) as image:
        binary = image.convert("L").point(lambda pixel: 255 if pixel > 127 else 0)
        bbox = binary.getbbox()
        if bbox is None:
            raise ValueError(f"Empty silhouette: {path}")
        cropped = binary.crop(bbox)
        aspect = cropped.width / cropped.height
        resized = cropped.resize((max(1, round(aspect * 256)), 256), Image.Resampling.NEAREST)
        mask = np.asarray(resized) > 0
    height, width = mask.shape
    occupied = mask.sum(axis=1)
    active = occupied > 0
    left = mask.argmax(axis=1)
    right = width - 1 - mask[:, ::-1].argmax(axis=1)
    span = np.where(active, right - left + 1, 0) / height
    center = np.where(active, ((left + right) / 2 - (width - 1) / 2) / height, 0)
    samples = np.linspace(0, height - 1, PROFILE_BINS)
    profiles = [np.interp(samples, np.arange(height), profile)
                for profile in (span, occupied / height, center)]
    return np.concatenate(profiles + [[aspect, mask.sum() / height**2, mask.mean()]])


def extract_split(data_root, split, workers):
    root = data_root / split
    metadata = {row["subject_id"]: row for row in read_csv(root / "hwg_metadata.csv")}
    measurements = {row["subject_id"]: row for row in read_csv(root / "measurements.csv")}
    mapping = sorted(read_csv(root / "subject_to_photo_map.csv"), key=lambda row: (row["subject_id"], row["photo_id"]))

    def extract(row):
        subject = row["subject_id"]
        info = metadata[subject]
        if info["gender"] not in ("male", "female"):
            raise ValueError(f"Unknown gender label for {subject}")
        known = np.array([float(info["height_cm"]), float(info["weight_kg"]), float(info["gender"] == "male")])
        shape = [silhouette_features(root / view / (row["photo_id"] + ".png")) for view in VIEWS]
        target = [float(measurements[subject][name]) for name in TARGETS]
        return np.concatenate([known] + shape), target

    features, targets = [], []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for number, (feature, target) in enumerate(executor.map(extract, mapping), 1):
            features.append(feature)
            targets.append(target)
            if number % 1000 == 0 or number == len(mapping):
                print(f"{split}: extracted {number:,}/{len(mapping):,} image pairs", flush=True)
    result = {
        "X": np.asarray(features), "y": np.asarray(targets),
        "subject_ids": np.array([row["subject_id"] for row in mapping]),
        "photo_ids": np.array([row["photo_id"] for row in mapping]),
    }
    if not np.isfinite(result["X"]).all() or not np.isfinite(result["y"]).all():
        raise ValueError(f"{split}: non-finite features or labels")
    if result["X"].shape[1] != len(FEATURE_NAMES):
        raise ValueError("Feature schema mismatch")
    return result


def subject_weights(ids):
    counts = Counter(ids)
    return np.array([1 / counts[subject] for subject in ids])


def metrics(y, prediction, ids):
    weights = subject_weights(ids)
    error = prediction - y
    mae = np.average(np.abs(error), axis=0, weights=weights)
    rmse = np.sqrt(np.average(error**2, axis=0, weights=weights))
    return {
        "subjects": len(set(ids)), "photo_pairs": len(ids),
        "mean_mae_cm": float(mae.mean()),
        "mae_cm": dict(zip(TARGETS, map(float, mae))),
        "rmse_cm": dict(zip(TARGETS, map(float, rmse))),
    }


def fit_ridge(X, y, ids, alpha):
    weights = subject_weights(ids)
    # Normalize to mean one so alpha does not depend on an arbitrary weight scale.
    weights /= weights.mean()
    scaler = StandardScaler().fit(X, sample_weight=weights)
    regressor = Ridge(alpha=alpha).fit(scaler.transform(X), y, sample_weight=weights)
    return scaler, regressor


def predict(model, X):
    scaler, regressor = model
    return regressor.predict(scaler.transform(X))


def write_predictions(path, data, prediction):
    fields = ["subject_id", "photo_id"]
    fields += [f"{target}_{suffix}_cm" for target in TARGETS for suffix in ("true", "pred", "abs_error")]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for subject, photo, truth, estimate in zip(data["subject_ids"], data["photo_ids"], data["y"], prediction):
            row = {"subject_id": subject, "photo_id": photo}
            for target, actual, predicted in zip(TARGETS, truth, estimate):
                row.update({f"{target}_true_cm": actual, f"{target}_pred_cm": predicted,
                            f"{target}_abs_error_cm": abs(actual - predicted)})
            writer.writerow(row)


def plot_results(report, path):
    names = ("mean_baseline", "metadata_ridge", "silhouette_metadata_ridge")
    labels = ("Training mean", "Height / weight / sex", "Silhouettes + metadata")
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for axis, split in zip(axes, ("testA", "testB")):
        positions = np.arange(len(TARGETS))
        for index, (name, label) in enumerate(zip(names, labels)):
            values = [report["results"][name][split]["mae_cm"][target] for target in TARGETS]
            axis.bar(positions + (index - 1) * 0.25, values, 0.25, label=label)
        axis.set_xticks(positions, [name.capitalize() for name in TARGETS])
        axis.set_title(f"{split} ({report['results'][names[0]][split]['subjects']} subjects)")
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Subject-balanced mean absolute error (cm)")
    axes[1].legend(fontsize=8)
    figure.suptitle("BodyM baseline: chest, waist and hip measurements")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/raw/bodym")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/bodym_baseline")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    processed = ROOT / "data/processed/bodym"
    processed.mkdir(parents=True, exist_ok=True)
    datasets = {split: extract_split(args.data_root, split, args.workers) for split in ("train", "testA", "testB")}
    for split, data in datasets.items():
        np.savez_compressed(processed / f"{split}_features.npz", **data, feature_names=FEATURE_NAMES, target_names=TARGETS)
    train = datasets["train"]
    subjects = np.array(sorted(set(train["subject_ids"])))
    np.random.default_rng(args.seed).shuffle(subjects)
    validation_subjects = set(subjects[:round(len(subjects) * 0.2)])
    validation_mask = np.array([subject in validation_subjects for subject in train["subject_ids"]])
    fitting_mask = ~validation_mask
    for split in ("testA", "testB"):
        if set(train["subject_ids"]) & set(datasets[split]["subject_ids"]):
            raise ValueError(f"Training subjects overlap {split}")
    for left, right in (("train", "testA"), ("train", "testB"), ("testA", "testB")):
        if set(datasets[left]["photo_ids"]) & set(datasets[right]["photo_ids"]):
            raise ValueError(f"Photo IDs overlap between {left} and {right}")
    split_record = {"seed": args.seed, "fit_subject_ids": sorted(set(train["subject_ids"][fitting_mask])),
                    "validation_subject_ids": sorted(validation_subjects)}
    (args.output / "subject_split.json").write_text(json.dumps(split_record, indent=2) + "\n", encoding="utf-8")
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed, "targets": list(TARGETS), "feature_count": len(FEATURE_NAMES),
        "fit_subjects": len(split_record["fit_subject_ids"]), "validation_subjects": len(validation_subjects),
        "metric_definition": "Mean absolute error over photo pairs within each subject, then mean over subjects; RMSE uses subject-balanced squared errors.",
        "protocol": "Choose alpha on 20% subject-disjoint validation from train, refit on all train, evaluate testA and testB separately.",
        "test_subject_overlap": len(set(datasets["testA"]["subject_ids"]) & set(datasets["testB"]["subject_ids"])),
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "scikit-learn": sklearn.__version__, "Pillow": PIL.__version__, "matplotlib": matplotlib.__version__},
        "results": {}, "validation_search": {},
    }
    train_weights = subject_weights(train["subject_ids"][fitting_mask])
    fitting_mean = np.average(train["y"][fitting_mask], axis=0, weights=train_weights)
    final_mean = np.average(train["y"], axis=0, weights=subject_weights(train["subject_ids"]))
    report["results"]["mean_baseline"] = {
        "validation": metrics(train["y"][validation_mask], np.tile(fitting_mean, (validation_mask.sum(), 1)), train["subject_ids"][validation_mask])
    }
    for split in ("testA", "testB"):
        data = datasets[split]
        report["results"]["mean_baseline"][split] = metrics(data["y"], np.tile(final_mean, (len(data["y"]), 1)), data["subject_ids"])
    artifacts = {"target_names": TARGETS, "feature_names": FEATURE_NAMES, "mean_baseline": final_mean}
    for name, columns in (("metadata_ridge", 3), ("silhouette_metadata_ridge", len(FEATURE_NAMES))):
        X = train["X"][:, :columns]
        search = []
        candidates = []
        for alpha in (0.1, 1.0, 10.0, 100.0, 1000.0):
            model = fit_ridge(X[fitting_mask], train["y"][fitting_mask], train["subject_ids"][fitting_mask], alpha)
            score = metrics(train["y"][validation_mask], predict(model, X[validation_mask]), train["subject_ids"][validation_mask])
            search.append({"alpha": alpha, "mean_mae_cm": score["mean_mae_cm"]})
            candidates.append((score["mean_mae_cm"], alpha, score))
        _, best_alpha, validation_result = min(candidates, key=lambda item: item[0])
        model = fit_ridge(X, train["y"], train["subject_ids"], best_alpha)
        report["validation_search"][name] = search
        report["results"][name] = {"alpha": best_alpha, "validation": validation_result}
        artifacts[name] = {"columns": columns, "model": model}
        for split in ("testA", "testB"):
            data = datasets[split]
            prediction = predict(model, data["X"][:, :columns])
            report["results"][name][split] = metrics(data["y"], prediction, data["subject_ids"])
            write_predictions(args.output / f"{split}_{name}_predictions.csv", data, prediction)
        print(f"{name}: selected alpha={best_alpha}, validation MAE={validation_result['mean_mae_cm']:.3f} cm", flush=True)
    model_directory = ROOT / "models/bodym_baseline"
    model_directory.mkdir(parents=True, exist_ok=True)
    with (model_directory / "ridge_models.pkl").open("wb") as handle:
        pickle.dump(artifacts, handle)
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_results(report, args.output / "mae_comparison.png")
    lines = ["# BodyM baseline run", "", f"Fit: {report['fit_subjects']} subjects; validation: {report['validation_subjects']} subjects.",
             "", "Targets: chest, waist, hip (cm). Test models refitted on all 2,018 training subjects.",
             "", "MAE below gives each subject equal weight, including subjects with multiple photos.", "",
             "| Model | Split | Chest MAE (cm) | Waist MAE (cm) | Hip MAE (cm) | Mean MAE (cm) |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for name, splits in report["results"].items():
        for split in ("validation", "testA", "testB"):
            score = splits[split]
            values = [score["mae_cm"][target] for target in TARGETS] + [score["mean_mae_cm"]]
            lines.append(f"| {name} | {split} | " + " | ".join(f"{value:.3f}" for value in values) + " |")
    lines += ["", "![MAE comparison](mae_comparison.png)", "", "Limitations:",
              "- Uses supplied height, weight and sex metadata as inputs; this is not an image-only model.",
              "- Uses simple silhouette profiles and Ridge regression, not the published BMnet model.",
              "- Original testA and testB share one subject ID; report their results separately.",
              "- Does not predict InBody values, body-fat percentage or skeletal muscle mass.",
              "- The score is an initial experiment, not a clinical validation.", ""]
    (args.output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
