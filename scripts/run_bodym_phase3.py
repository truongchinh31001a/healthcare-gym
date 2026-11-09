"""Phase 3: matched ablations and calibration on subjects excluded from new fits."""
import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
import torch
from torch import nn

from bodym_cnn import TARGETS, METADATA, PREPROCESS_VERSION, fit_normalization, calibrate_batchnorm
from run_bodym_cnn import load_split, validate_splits, seed_everything, tensor_data, predictions
from run_bodym_phase2 import reuse_verified_audit, sha, dump
from src.body_vision.analysis import score, fit_subgroup_bins, subgroup_scores
from src.multimodal.model import AblationModel, load_ablation
from src.multimodal.calibration import fit_calibrator, interval_metrics
from src.multimodal.ood import novelty_features, fit_novelty, novelty_flags


def make_split(original, seed, fraction):
    if not 0 < fraction < 1:
        raise ValueError("Calibration fraction must be in (0,1)")
    subjects = np.array(sorted(original["fit_subject_ids"]))
    np.random.default_rng(seed).shuffle(subjects)
    count = round(len(subjects) * fraction)
    if not 1 <= count < len(subjects):
        raise ValueError("Proper-fit and calibration splits must both contain subjects")
    record = {"split_seed": seed, "proper_fit_subject_ids": sorted(subjects[count:].tolist()),
              "tuning_subject_ids": sorted(original["validation_subject_ids"]),
              "calibration_subject_ids": sorted(subjects[:count].tolist())}
    validate_phase3_split(record, set(original["fit_subject_ids"]) | set(original["validation_subject_ids"]))
    return record


def validate_phase3_split(record, train_ids):
    keys = ("proper_fit_subject_ids", "tuning_subject_ids", "calibration_subject_ids")
    groups = [set(record[key]) for key in keys]
    if any(not group or len(group) != len(record[key]) for group, key in zip(groups, keys)):
        raise ValueError("Empty/duplicate subject split")
    if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)) or set.union(*groups) != set(train_ids):
        raise ValueError("Phase 3 subjects must partition original train without overlap")


def checkpoint_payload(model, config, normalization, variant, epoch, phase, trained_ids, tuning_ids, split_sha):
    return {"state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
            "config": config, "normalization": normalization, "variant": variant, "epoch": epoch, "phase": phase,
            "targets": list(TARGETS), "metadata_names": list(METADATA), "preprocess_version": PREPROCESS_VERSION,
            "trained_subject_ids": sorted(set(map(str, trained_ids))), "tuning_subject_ids": sorted(tuning_ids),
            "split_sha256": split_sha}


def train(variant, config, training, validation, validation_data, normalization, device, directory,
          trained_ids, tuning_ids, split_sha, epochs, phase):
    seed_everything(config["seed"])
    model = AblationModel(config, variant).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    loss_fn = nn.SmoothL1Loss(beta=config["huber_beta"], reduction="none")
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    rng = np.random.default_rng(config["seed"])
    best, best_epoch, stale, history = float("inf"), 0, 0, []
    for epoch in range(1, epochs + 1):
        start = time.perf_counter()
        rate = config["min_learning_rate"] + (config["learning_rate"] - config["min_learning_rate"]) * (1 + math.cos(math.pi * (epoch - 1) / max(config["max_epochs"] - 1, 1))) / 2
        for group in optimizer.param_groups:
            group["lr"] = rate
        model.train()
        order = rng.permutation(len(training["images"]))
        total = 0
        for offset in range(0, len(order), config["batch_size"]):
            index = torch.tensor(order[offset:offset + config["batch_size"]], device=device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                output = model(training["images"][index].float(), training["metadata"][index])
                loss = (loss_fn(output, training["targets"][index]).mean(dim=1) * training["weights"][index]).mean()
            if not torch.isfinite(loss):
                raise RuntimeError("Nonfinite training loss")
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 5)
            scaler.step(optimizer)
            scaler.update()
            total += float(loss.detach()) * len(index)
        if model.encoder is not None and config["calibrate_batchnorm"]:
            calibrate_batchnorm(model, training["images"], config["batch_size"])
        row = {"epoch": epoch, "learning_rate": rate, "train_huber": total / len(order)}
        if validation is not None:
            pred = predictions(model, validation, normalization, config["batch_size"])
            metric = score(validation_data["y"], pred, validation_data["subject_ids"])["mean_mae_cm"]
            row["tuning_mae_cm"] = metric
            if metric < best - 1e-4:
                best, best_epoch, stale = metric, epoch, 0
                torch.save(checkpoint_payload(model, config, normalization, variant, epoch, phase, trained_ids, tuning_ids, split_sha), directory / "selection_best.pt")
            else:
                stale += 1
        else:
            best_epoch = epoch
        row["seconds"] = time.perf_counter() - start
        history.append(row)
        dump(directory / f"{phase}_history.json", history)
        if epoch == 1 or epoch % 5 == 0 or epoch == epochs:
            print(f"{variant}/{phase} {epoch}/{epochs}: loss={row['train_huber']:.4f}" +
                  (f", tune MAE={row['tuning_mae_cm']:.3f}" if validation is not None else ""), flush=True)
        if validation is not None and stale >= config["patience"]:
            break
    return model, best_epoch, best, history


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/bodym_phase3.json")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--evaluate-only", action="store_true", help="Reuse new Phase 3 checkpoints/calibrators; no training or recalibration")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    cnn_config = json.loads((ROOT / config["base_config"]).read_text(encoding="utf-8"))
    if cnn_config["seed"] != config["seed"]:
        raise ValueError("Seeds differ")
    torch.set_num_threads(cnn_config["cpu_threads"])
    device = torch.device(("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device)
    default_config_sha = sha(ROOT / "configs/default_model.json")
    default_checkpoint = ROOT / json.loads((ROOT / "configs/default_model.json").read_text())["checkpoint"]
    default_checkpoint_sha = sha(default_checkpoint)
    # Verify actual source hashes against the completed Phase 2 audit without rerunning mask components.
    phase2_config = json.loads((ROOT / "configs/bodym_phase2.json").read_text())
    if config["data_root"] != phase2_config["data_root"]:
        raise ValueError("Phase 3 data root must match the verified Phase 2 source")
    manifest = reuse_verified_audit(phase2_config)
    datasets = {split: load_split(ROOT / config["data_root"], split, cnn_config) for split in ("train", "testA", "testB")}
    original = json.loads((ROOT / config["outer_split"]).read_text())
    validate_splits(datasets, original)
    record = make_split(original, config["calibration_split_seed"], config["calibration_fraction_of_original_fit"])
    validate_phase3_split(record, datasets["train"]["subject_ids"])
    output, model_root = ROOT / config["output"], ROOT / config["model_dir"]
    output.mkdir(parents=True, exist_ok=True)
    split_path = output / "subject_split.json"
    if split_path.exists() and json.loads(split_path.read_text()) != record:
        raise ValueError("Existing Phase 3 split differs; use a separate experiment directory")
    dump(split_path, record)
    split_sha = sha(split_path)
    train_data = datasets["train"]
    masks = {name: np.isin(train_data["subject_ids"], record[name + "_subject_ids"]) for name in ("proper_fit", "tuning", "calibration")}
    masks["refit"] = masks["proper_fit"] | masks["tuning"]
    proper_norm = fit_normalization(train_data["metadata"][masks["proper_fit"]], train_data["y"][masks["proper_fit"]], train_data["subject_ids"][masks["proper_fit"]])
    final_norm = fit_normalization(train_data["metadata"][masks["refit"]], train_data["y"][masks["refit"]], train_data["subject_ids"][masks["refit"]])
    bins = fit_subgroup_bins(train_data["metadata"][masks["proper_fit"]], train_data["subject_ids"][masks["proper_fit"]])
    novelty_path = model_root / "novelty.json"
    if not args.evaluate_only:
        features = novelty_features(train_data["images"][masks["proper_fit"]], train_data["metadata"][masks["proper_fit"]])
        novelty = fit_novelty(features, train_data["subject_ids"][masks["proper_fit"]], config["ood_training_quantile"])
        novelty.update(split_sha256=split_sha, preprocessing_version=PREPROCESS_VERSION)
        dump(novelty_path, novelty)
    novelty = json.loads(novelty_path.read_text())
    if novelty["split_sha256"] != split_sha:
        raise ValueError("Novelty detector belongs to a different split")
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config, "training_config": cnn_config,
              "split_sha256": split_sha, "subject_counts": {name: len(record[name + "_subject_ids"]) for name in ("proper_fit", "tuning", "calibration")},
              "refit_subjects": int(len(np.unique(train_data["subject_ids"][masks["refit"]]))),
              "source_image_inventory_sha256": manifest["image_inventory_sha256"], "default_checkpoint_sha256": default_checkpoint_sha,
              "default_config_sha256": default_config_sha, "subgroup_bins": bins,
              "versions": {"torch": torch.__version__, "numpy": np.__version__}, "device": str(device),
              "results": {}, "ood": {}, "default_model_changed": False,
              "note": "New research checkpoints trained with calibration excluded. Do not attach their intervals to the default all-train checkpoint.",
              "historical_reuse": "Architecture/hyperparameters and test sets were explored in earlier phases; this is not a pristine prospective benchmark."}
    for split in ("testA", "testB"):
        data = datasets[split]
        values = novelty_flags(novelty_features(data["images"], data["metadata"]), novelty)
        report["ood"][split] = {"photo_pairs": len(data["y"]), "flagged_pairs": int(values["flagged"].sum()),
            "subjects_with_any_flag": len(set(data["subject_ids"][values["flagged"]])),
            "pair_flag_rate": float(values["flagged"].mean()), "distance_threshold": novelty["threshold"],
            "interpretation": "Novelty heuristic only; no OOD ground-truth or calibrated probability"}
    for variant in config["variants"]:
        directory, model_dir = output / variant, model_root / variant
        directory.mkdir(parents=True, exist_ok=True)
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "model.pt"
        if not args.evaluate_only:
            # Refuse accidental overwrite of a finished research checkpoint.
            if model_path.exists():
                raise FileExistsError(f"Checkpoint exists; use --evaluate-only or a new output/model directory: {model_path}")
            training = tensor_data(train_data, proper_norm, device, masks["proper_fit"])
            validation = tensor_data(train_data, proper_norm, device, masks["tuning"])
            validation_data = {key: train_data[key][masks["tuning"]] for key in ("y", "subject_ids")}
            selected, epoch, best, history = train(variant, cnn_config, training, validation, validation_data,
                proper_norm, device, directory, train_data["subject_ids"][masks["proper_fit"]], record["tuning_subject_ids"],
                split_sha, cnn_config["max_epochs"], "selection")
            del selected, training, validation
            if device.type == "cuda":
                torch.cuda.empty_cache()
            refit = tensor_data(train_data, final_norm, device, masks["refit"])
            model, _, _, refit_history = train(variant, cnn_config, refit, None, None, final_norm, device,
                directory, train_data["subject_ids"][masks["refit"]], record["tuning_subject_ids"], split_sha, epoch, "refit")
            payload = checkpoint_payload(model, cnn_config, final_norm, variant, epoch, "refit_without_calibration",
                train_data["subject_ids"][masks["refit"]], record["tuning_subject_ids"], split_sha)
            torch.save(payload, model_path)
            dump(directory / "selection.json", {"selected_epoch": epoch, "tuning_mean_mae_cm": best,
                "selection_epochs_run": len(history), "training_seconds": sum(row["seconds"] for row in history + refit_history)})
            del model, refit
        model, checkpoint = load_ablation(model_path, device)
        expected_trained = set(map(str, train_data["subject_ids"][masks["refit"]]))
        if set(checkpoint["trained_subject_ids"]) != expected_trained or checkpoint["split_sha256"] != split_sha or checkpoint["variant"] != variant or checkpoint["config"] != cnn_config:
            raise ValueError("Training provenance differs from experiment protocol")
        for key in final_norm:
            np.testing.assert_allclose(checkpoint["normalization"][key], final_norm[key], atol=1e-6, rtol=1e-6)
        model_sha = sha(model_path)
        cal_path = model_dir / "calibration.json"
        if not args.evaluate_only:
            tensors = tensor_data(train_data, checkpoint["normalization"], device, masks["calibration"])
            cal_prediction = predictions(model, tensors, checkpoint["normalization"], cnn_config["batch_size"])
            calibrator = fit_calibrator(train_data["y"][masks["calibration"]], cal_prediction,
                train_data["subject_ids"][masks["calibration"]], alpha=config["alpha"],
                trained_ids=checkpoint["trained_subject_ids"], tuned_ids=checkpoint["tuning_subject_ids"], checkpoint_sha256=model_sha)
            calibrator.update(split_sha256=split_sha)
            dump(cal_path, calibrator)
            del tensors
        calibrator = json.loads(cal_path.read_text())
        if calibrator["checkpoint_sha256"] != model_sha or calibrator["split_sha256"] != split_sha or calibrator["alpha"] != config["alpha"]:
            raise ValueError("Calibrator/model/protocol mismatch")
        result = {"parameters": sum(p.numel() for p in model.parameters()), "checkpoint_sha256": model_sha,
                  "selection": json.loads((directory / "selection.json").read_text()), "calibrator": calibrator, "tests": {}}
        for split in ("testA", "testB"):
            data = datasets[split]
            tensors = tensor_data(data, checkpoint["normalization"], device)
            pred = predictions(model, tensors, checkpoint["normalization"], cnn_config["batch_size"])
            novelty_result = novelty_flags(novelty_features(data["images"], data["metadata"]), novelty)
            metric = {"point": score(data["y"], pred, data["subject_ids"]),
                      "interval": interval_metrics(data["y"], pred, data["subject_ids"], calibrator),
                      "subgroups": subgroup_scores(data["y"], pred, data["subject_ids"], data["metadata"], bins)}
            # OOD diagnostics never filter the overall test score.
            for flag, mask in (("flagged", novelty_result["flagged"]), ("unflagged", ~novelty_result["flagged"])):
                metric[flag] = {"point": score(data["y"][mask], pred[mask], data["subject_ids"][mask]),
                               "interval": interval_metrics(data["y"][mask], pred[mask], data["subject_ids"][mask], calibrator)} if mask.any() else None
            result["tests"][split] = metric
            private = ROOT / "data/processed/bodym_phase3" / variant
            private.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(private / f"{split}_predictions.npz", prediction=pred, y=data["y"],
                                subject_ids=data["subject_ids"], photo_ids=data["photo_ids"], ood_flag=novelty_result["flagged"])
            print(f"{variant}/{split}: MAE={metric['point']['mean_mae_cm']:.3f}; joint subject coverage={metric['interval']['joint_subject_all_targets_all_photos_coverage']:.3f}", flush=True)
            del tensors
        report["results"][variant] = result
        dump(output / "metrics.partial.json", report)
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
    if sha(default_checkpoint) != default_checkpoint_sha or sha(ROOT / "configs/default_model.json") != default_config_sha:
        raise ValueError("Default model/config changed")
    dump(output / "metrics.json", report)
    from report_bodym_phase3 import write_artifacts
    write_artifacts(report, output, model_root)
    print(f"Phase 3 complete: {output / 'report.md'}", flush=True)


if __name__ == "__main__":
    run()
