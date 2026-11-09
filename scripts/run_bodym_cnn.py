"""Train a custom two-view BodyM CNN; select on validation, refit, then test."""

import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn

from bodym_cnn import (ROOT, TARGETS, VIEWS, PREPROCESS_VERSION, TwoViewBodyCNN,
                       calibrate_batchnorm, fit_normalization, load_model, predict_pair, preprocess_silhouette)
from run_bodym_baseline import metrics, read_csv, subject_weights, write_predictions


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


def load_split(data_root, split, config):
    root = data_root / split
    digest = hashlib.sha256()
    for name in ("hwg_metadata.csv", "measurements.csv", "subject_to_photo_map.csv"):
        digest.update((root / name).read_bytes())
    manifest = data_root / "download_manifest.json"
    if manifest.exists():
        digest.update(manifest.read_bytes())
    preprocessing = {name: config[name] for name in ("image_height", "image_width", "padding")}
    digest.update(json.dumps([PREPROCESS_VERSION, preprocessing], sort_keys=True).encode())
    fingerprint = digest.hexdigest()
    cache_root = ROOT / "data/processed/bodym"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / f"cnn_{config['image_height']}x{config['image_width']}_{split}.npz"
    if cache_path.exists():
        with np.load(cache_path) as cached:
            if str(cached["fingerprint"]) == fingerprint:
                result = {key: cached[key].copy() for key in ("images", "metadata", "y", "subject_ids", "photo_ids")}
                print(f"{split}: loaded {len(result['y']):,} cached image pairs", flush=True)
                return result
    metadata = {row["subject_id"]: row for row in read_csv(root / "hwg_metadata.csv")}
    labels = {row["subject_id"]: row for row in read_csv(root / "measurements.csv")}
    mapping = sorted(read_csv(root / "subject_to_photo_map.csv"), key=lambda row: (row["subject_id"], row["photo_id"]))
    images = np.empty((len(mapping), 2, 1, config["image_height"], config["image_width"]), dtype=np.uint8)

    def process(row):
        return np.stack([preprocess_silhouette(root / view / (row["photo_id"] + ".png"), config) for view in VIEWS])

    with ThreadPoolExecutor(max_workers=config["preprocess_workers"]) as executor:
        for index, image in enumerate(executor.map(process, mapping)):
            images[index] = image
            if (index + 1) % 1000 == 0 or index + 1 == len(mapping):
                print(f"{split}: preprocessed {index + 1:,}/{len(mapping):,} pairs", flush=True)
    known, targets = [], []
    for row in mapping:
        subject = row["subject_id"]
        info = metadata[subject]
        if info["gender"] not in ("male", "female"):
            raise ValueError(f"Unexpected gender label for {subject}")
        known.append([float(info["height_cm"]), float(info["weight_kg"]), float(info["gender"] == "male")])
        targets.append([float(labels[subject][target]) for target in TARGETS])
    result = {"images": images, "metadata": np.asarray(known, dtype=np.float32),
              "y": np.asarray(targets, dtype=np.float32),
              "subject_ids": np.array([row["subject_id"] for row in mapping]),
              "photo_ids": np.array([row["photo_id"] for row in mapping])}
    np.savez_compressed(cache_path, **result, fingerprint=fingerprint)
    return result


def validate_splits(datasets, record):
    fitting, validation = set(record["fit_subject_ids"]), set(record["validation_subject_ids"])
    train = set(datasets["train"]["subject_ids"])
    if fitting & validation or fitting | validation != train:
        raise ValueError("Fit/validation subjects must partition the training split")
    for split in ("testA", "testB"):
        if train & set(datasets[split]["subject_ids"]):
            raise ValueError(f"Training subjects overlap {split}")
    for left, right in (("train", "testA"), ("train", "testB"), ("testA", "testB")):
        if set(datasets[left]["photo_ids"]) & set(datasets[right]["photo_ids"]):
            raise ValueError(f"Photo IDs overlap {left} and {right}")


def tensor_data(data, normalization, device, selection=None):
    if selection is None:
        selection = slice(None)
    metadata = (data["metadata"][selection] - normalization["metadata_mean"]) / normalization["metadata_std"]
    targets = (data["y"][selection] - normalization["target_mean"]) / normalization["target_std"]
    weights = subject_weights(data["subject_ids"][selection])
    weights /= weights.mean()
    return {
        "images": torch.as_tensor(data["images"][selection], device=device),
        "metadata": torch.tensor(metadata, dtype=torch.float32, device=device),
        "targets": torch.tensor(targets, dtype=torch.float32, device=device),
        "weights": torch.tensor(weights, dtype=torch.float32, device=device),
    }


@torch.inference_mode()
def predictions(model, tensors, normalization, batch_size):
    model.eval()
    output = []
    for start in range(0, len(tensors["images"]), batch_size):
        stop = start + batch_size
        result = model(tensors["images"][start:stop].float(), tensors["metadata"][start:stop])
        output.append(result.cpu().numpy())
    return np.concatenate(output) * normalization["target_std"] + normalization["target_mean"]


def checkpoint(model, config, normalization, epoch, phase):
    return {"state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
            "config": config, "normalization": normalization, "epoch": epoch, "phase": phase,
            "targets": list(TARGETS), "preprocess_version": PREPROCESS_VERSION,
            "architecture": "Shared Conv16-32-64-128 + GAP; metadata MLP; fusion MLP"}


def train_phase(training, validation, data, config, normalization, device, directory, phase, epochs):
    seed_everything(config["seed"])
    model = TwoViewBodyCNN(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    criterion = nn.SmoothL1Loss(beta=config["huber_beta"], reduction="none")
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    history, best_mae, best_epoch, stale = [], float("inf"), 0, 0
    rng = np.random.default_rng(config["seed"])
    batch_size = config["batch_size"]
    for epoch in range(1, epochs + 1):
        started = time.perf_counter()
        # Refit replays the same predeclared LR curve up to the selected epoch.
        fraction = (epoch - 1) / max(config["max_epochs"] - 1, 1)
        rate = config["min_learning_rate"] + (config["learning_rate"] - config["min_learning_rate"]) * (1 + math.cos(math.pi * fraction)) / 2
        for group in optimizer.param_groups:
            group["lr"] = rate
        model.train()
        order = rng.permutation(len(training["images"]))
        loss_sum = 0.0
        for start in range(0, len(order), batch_size):
            indices = torch.tensor(order[start:start + batch_size], device=device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                prediction = model(training["images"][indices].float(), training["metadata"][indices])
                per_pair = criterion(prediction, training["targets"][indices]).mean(dim=1)
                loss = (per_pair * training["weights"][indices]).mean()
            if not torch.isfinite(loss):
                raise RuntimeError(f"Non-finite loss in {phase}, epoch {epoch}")
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(optimizer)
            scaler.update()
            loss_sum += float(loss.detach()) * len(indices)
        if config.get("calibrate_batchnorm", False):
            calibrate_batchnorm(model, training["images"], batch_size)
        row = {"epoch": epoch, "learning_rate": rate, "train_huber": loss_sum / len(order)}
        if validation is not None:
            estimated = predictions(model, validation, normalization, batch_size)
            result = metrics(data["y"], estimated, data["subject_ids"])
            row["validation_mae_cm"] = result["mean_mae_cm"]
            if result["mean_mae_cm"] < best_mae - 1e-4:
                best_mae, best_epoch, stale = result["mean_mae_cm"], epoch, 0
                torch.save(checkpoint(model, config, normalization, epoch, phase), directory / "selection_best.pt")
            else:
                stale += 1
        else:
            best_epoch = epoch
        row["seconds"] = time.perf_counter() - started
        history.append(row)
        (directory / f"{phase}_history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
        suffix = f", validation MAE={row['validation_mae_cm']:.3f} cm, best={best_mae:.3f}" if validation is not None else ""
        print(f"{phase} {epoch:02d}/{epochs}: loss={row['train_huber']:.5f}{suffix}, {row['seconds']:.1f}s", flush=True)
        if validation is not None and stale >= config["patience"]:
            print(f"Early stopping; selected epoch {best_epoch}", flush=True)
            break
    return model, history, best_epoch


def write_report(report, output):
    lines = ["# BodyM custom CNN", "",
             "Two silhouette views share a four-block CNN (16/32/64/128 channels, BatchNorm, ReLU, MaxPool, Global Average Pooling).",
             "Height, weight and sex pass through a 3 -> 32 -> 16 MLP; fusion is 272 -> 128 -> 64 -> 3 with dropout.", "",
             f"Device: {report['device']}; parameters: {report['parameters']:,}; selected epoch: {report['selected_epoch']}.",
             "", "The best epoch is selected using the same 1,614/404-subject fit/validation split as Ridge.",
             "The network is then initialized again and trained on all 2,018 train subjects for that many epochs.",
             "Metadata and targets are normalized using only the training subjects of each phase.",
             "BatchNorm statistics are recalibrated using only training images after each epoch at fixed weights.",
             "Huber loss and MAE give each subject equal total weight. TestA and testB remain separate.", "",
             "| Model | Split | Chest MAE (cm) | Waist MAE (cm) | Hip MAE (cm) | Mean MAE (cm) |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for name, results in report["comparison"].items():
        for split in ("validation", "testA", "testB"):
            score = results[split]
            values = [score["mae_cm"][target] for target in TARGETS] + [score["mean_mae_cm"]]
            lines.append(f"| {name} | {split} | " + " | ".join(f"{value:.3f}" for value in values) + " |")
    lines += ["", "![Training history](training_history.png)", "", "![Test comparison](mae_comparison.png)", "",
              "This is one initial run of a custom architecture. Inputs include supplied metadata and binary silhouettes.",
              "Original testA and testB share one subject ID. The model predicts circumferences, not InBody fat/muscle values.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def plot_results(report, selection_history, refit_history, output):
    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot([r["epoch"] for r in selection_history], [r["train_huber"] for r in selection_history], label="Selection fit")
    axes[0].plot([r["epoch"] for r in refit_history], [r["train_huber"] for r in refit_history], label="Refit all train")
    axes[0].set(xlabel="Epoch", ylabel="Subject-balanced standardized Huber loss")
    axes[0].legend()
    axes[1].plot([r["epoch"] for r in selection_history], [r["validation_mae_cm"] for r in selection_history])
    axes[1].axvline(report["selected_epoch"], color="tab:red", linestyle="--", label="Selected epoch")
    axes[1].set(xlabel="Epoch", ylabel="Validation MAE (cm)")
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(output / "training_history.png", dpi=160)
    plt.close(figure)
    figure, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    available = [(name, label) for name, label in (
        ("metadata_ridge", "Metadata Ridge"),
        ("silhouette_metadata_ridge", "Silhouette + metadata Ridge"),
        ("two_view_cnn", "Custom CNN + metadata"),
    ) if name in report["comparison"]]
    for axis, split in zip(axes, ("testA", "testB")):
        positions = np.arange(len(TARGETS))
        for index, (name, label) in enumerate(available):
            values = [report["comparison"][name][split]["mae_cm"][target] for target in TARGETS]
            axis.bar(positions + (index - (len(available) - 1) / 2) * 0.25, values, 0.25, label=label)
        axis.set_xticks(positions, [target.capitalize() for target in TARGETS])
        axis.set_title(split)
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Subject-balanced MAE (cm)")
    axes[1].legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(output / "mae_comparison.png", dpi=160)
    plt.close(figure)


def main(default_config=None, default_subject_split=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config or ROOT / "configs/bodym_cnn.json")
    parser.add_argument("--subject-split", type=Path, default=default_subject_split or ROOT / "configs/bodym_subject_split.json")
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/raw/bodym")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/bodym_cnn")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--evaluate-only", action="store_true", help="Evaluate existing selection/refit checkpoints without retraining")
    args = parser.parse_args()
    started = time.perf_counter()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    torch.set_num_threads(config["cpu_threads"])
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else ("cpu" if args.device == "auto" else args.device))
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but not available")
    print(f"PyTorch {torch.__version__}; device={device}", flush=True)
    if device.type == "cuda":
        print(torch.cuda.get_device_name(), flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    model_root = ROOT / "models/bodym_cnn"
    model_root.mkdir(parents=True, exist_ok=True)
    datasets = {split: load_split(args.data_root, split, config) for split in ("train", "testA", "testB")}
    train = datasets["train"]
    split_record = json.loads(args.subject_split.read_text(encoding="utf-8"))
    if split_record["seed"] != config["seed"]:
        raise ValueError("Config seed must match the fixed subject split")
    validate_splits(datasets, split_record)
    (args.output / "subject_split.json").write_text(json.dumps(split_record, indent=2) + "\n", encoding="utf-8")
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    fitting = np.isin(train["subject_ids"], split_record["fit_subject_ids"])
    validation = ~fitting
    validation_data = {key: value[validation] for key, value in train.items() if key != "images"}
    if args.evaluate_only:
        selection_history = json.loads((args.output / "selection_history.json").read_text())
        refit_history = json.loads((args.output / "refit_history.json").read_text())
    else:
        normalization = fit_normalization(train["metadata"][fitting], train["y"][fitting], train["subject_ids"][fitting])
        training_tensors = tensor_data(train, normalization, device, fitting)
        validation_tensors = tensor_data(train, normalization, device, validation)
        selection_model, selection_history, best_epoch = train_phase(
            training_tensors, validation_tensors, validation_data, config, normalization, device,
            args.output, "selection", config["max_epochs"])
        del selection_model, training_tensors, validation_tensors
    selected_model, selected_checkpoint = load_model(args.output / "selection_best.pt", device)
    if selected_checkpoint["config"] != config:
        raise ValueError("Selection checkpoint config differs from this run")
    normalization = selected_checkpoint["normalization"]
    best_epoch = selected_checkpoint["epoch"]
    validation_tensors = tensor_data(train, normalization, device, validation)
    validation_prediction = predictions(selected_model, validation_tensors, normalization, config["batch_size"])
    validation_metrics = metrics(validation_data["y"], validation_prediction, validation_data["subject_ids"])
    write_predictions(args.output / "validation_predictions.csv", validation_data, validation_prediction)
    del selected_model, validation_tensors
    if device.type == "cuda":
        torch.cuda.empty_cache()
    if args.evaluate_only:
        model, refit_checkpoint = load_model(model_root / "model.pt", device)
        if refit_checkpoint["config"] != config or refit_checkpoint["epoch"] != best_epoch:
            raise ValueError("Refit checkpoint does not match selected config/epoch")
        normalization = refit_checkpoint["normalization"]
    else:
        normalization = fit_normalization(train["metadata"], train["y"], train["subject_ids"])
        all_training = tensor_data(train, normalization, device)
        model, refit_history, _ = train_phase(all_training, None, None, config, normalization,
                                             device, args.output, "refit", best_epoch)
        torch.save(checkpoint(model, config, normalization, best_epoch, "refit_all_train"), model_root / "model.pt")
    (model_root / "architecture.txt").write_text(str(model) + "\n", encoding="utf-8")
    results = {"validation": validation_metrics}
    restored, _ = load_model(model_root / "model.pt", device)
    verification = {"same_subject_split_as_ridge": True, "train_test_subject_isolation": True,
                    "normalization_fit_scope": "fit subjects during selection; all train subjects during refit"}
    first_prediction = None
    for split in ("testA", "testB"):
        data = datasets[split]
        tensors = tensor_data(data, normalization, device)
        estimated = predictions(restored, tensors, normalization, config["batch_size"])
        # Match batch size as well as inputs: CUDA may select different convolution
        # kernels for batch 8 versus batch 64, which is not a checkpoint mismatch.
        count = min(config["batch_size"], len(data["y"]))
        original = predictions(model, {key: value[:count] for key, value in tensors.items()}, normalization, config["batch_size"])
        np.testing.assert_allclose(original, estimated[:count], atol=1e-6, rtol=1e-6)
        if not np.isfinite(estimated).all():
            raise RuntimeError("Non-finite prediction")
        results[split] = metrics(data["y"], estimated, data["subject_ids"])
        write_predictions(args.output / f"{split}_predictions.csv", data, estimated)
        # Independent subject-wise MAE check, rather than just reusing the metric helper.
        errors = np.abs(estimated - data["y"])
        independent = np.mean([errors[data["subject_ids"] == subject].mean(axis=0) for subject in np.unique(data["subject_ids"])], axis=0)
        np.testing.assert_allclose(independent, [results[split]["mae_cm"][target] for target in TARGETS], atol=1e-8)
        verification[f"{split}_restored_predictions_and_macro_mae"] = "passed"
        if split == "testA":
            first_prediction = estimated[0]
        del tensors
    example = datasets["testA"]
    example_metadata = example["metadata"][0]
    photo = str(example["photo_ids"][0])
    raw_prediction = predict_pair(model_root / "model.pt",
        args.data_root / "testA/mask" / (photo + ".png"), args.data_root / "testA/mask_left" / (photo + ".png"),
        float(example_metadata[0]), float(example_metadata[1]), "male" if example_metadata[2] else "female")
    raw_images = np.stack([preprocess_silhouette(args.data_root / "testA" / view / (photo + ".png"), config) for view in VIEWS])
    np.testing.assert_array_equal(raw_images, example["images"][0])
    cpu_model, _ = load_model(model_root / "model.pt", "cpu")
    cpu_tensors = tensor_data(example, normalization, torch.device("cpu"), slice(0, 1))
    cpu_cached = predictions(cpu_model, cpu_tensors, normalization, batch_size=1)[0]
    np.testing.assert_allclose(list(raw_prediction.values()), cpu_cached, atol=1e-6, rtol=1e-6)
    # CPU vs CUDA/TF32 and different batch sizes use different convolution kernels.
    # Check input and checkpoint identity strictly above; allow 0.01 cm (0.1 mm)
    # for the cross-backend numerical comparison and record the actual difference.
    difference = float(np.max(np.abs(cpu_cached - first_prediction)))
    if difference > 0.01:
        raise RuntimeError(f"CPU/CUDA inference differs by {difference:.6f} cm")
    verification["raw_pair_preprocessing_and_same_backend_inference"] = "passed"
    verification["cpu_vs_batched_gpu_max_abs_difference_cm"] = difference
    verification["cpu_vs_batched_gpu_tolerance_cm"] = 0.01
    (args.output / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    comparison = {}
    baseline_path = ROOT / "experiments/bodym_baseline/metrics.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        comparison.update({name: baseline["results"][name] for name in ("metadata_ridge", "silhouette_metadata_ridge")})
    comparison["two_view_cnn"] = results
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config,
              "device": torch.cuda.get_device_name() if device.type == "cuda" else "CPU",
              "torch_version": str(torch.__version__), "parameters": sum(p.numel() for p in model.parameters()),
              "selected_epoch": best_epoch, "selection_epochs_run": len(selection_history),
              "fit_subjects": len(split_record["fit_subject_ids"]), "validation_subjects": len(split_record["validation_subject_ids"]),
              "final_train_subjects": len(set(train["subject_ids"])), "results": results,
              "test_subject_overlap": len(set(datasets["testA"]["subject_ids"]) & set(datasets["testB"]["subject_ids"])),
              "comparison": comparison,
              "training_seconds": sum(row["seconds"] for row in selection_history + refit_history),
              "evaluation_only": args.evaluate_only,
              "elapsed_seconds": time.perf_counter() - started}
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_results(report, selection_history, refit_history, args.output)
    write_report(report, args.output)
    print(json.dumps(results, indent=2), flush=True)
    print(f"Finished in {report['elapsed_seconds'] / 60:.1f} minutes: {args.output}", flush=True)


if __name__ == "__main__":
    main()
