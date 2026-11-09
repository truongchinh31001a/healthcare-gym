"""Audit all BodyM masks; evaluate the selected CNN without training or selection."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import PIL
import torch

from bodym_cnn import TARGETS, VIEWS, PREPROCESS_VERSION, load_model, preprocess_silhouette, fit_normalization
from run_bodym_cnn import load_split, validate_splits
from run_bodym_baseline import read_csv
from src.body_vision.analysis import score, fit_subgroup_bins, subgroup_scores
from src.body_vision.quality import assess_mask
from src.body_vision.perturbations import perturb


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def check_etag(content, record):
    expected = record["etag"].strip('"')
    if len(expected) != 32 or "-" in expected:
        raise ValueError("Expected the original single-part BodyM object ETag")
    if hashlib.md5(content, usedforsecurity=False).hexdigest() != expected or len(content) != record["size"]:
        raise ValueError(f"BodyM source integrity mismatch: {record['key']}")


def audit_dataset(config):
    data_root = ROOT / config["data_root"]
    source_manifest = data_root / "download_manifest.json"
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    objects = {record["key"]: record for record in source["files"]}
    jobs, csv_hashes, subjects, photos = [], {}, {}, {}
    split_record = json.loads((ROOT / config["subject_split"]).read_text(encoding="utf-8"))
    for split in ("train", "testA", "testB"):
        root = data_root / split
        metadata = read_csv(root / "hwg_metadata.csv")
        labels = read_csv(root / "measurements.csv")
        mapping = read_csv(root / "subject_to_photo_map.csv")
        subject_ids = [row["subject_id"] for row in metadata]
        if len(set(subject_ids)) != len(subject_ids) or len({row["subject_id"] for row in labels}) != len(labels):
            raise ValueError("Duplicate subject rows")
        if set(subject_ids) != {row["subject_id"] for row in labels} or set(subject_ids) != {row["subject_id"] for row in mapping}:
            raise ValueError("BodyM table-key mismatch")
        if any(row["gender"] not in ("male", "female") for row in metadata):
            raise ValueError("Unexpected provided gender value")
        if any(not np.isfinite(float(row[k])) or float(row[k]) <= 0 for row in metadata for k in ("height_cm", "weight_kg")):
            raise ValueError("Invalid metadata")
        if any(not np.isfinite(float(value)) or float(value) <= 0 for row in labels for key, value in row.items() if key != "subject_id"):
            raise ValueError("Invalid measurement label")
        photo_ids = {row["photo_id"] for row in mapping}
        if len(photo_ids) != len(mapping):
            raise ValueError("Duplicate photo mapping")
        subjects[split], photos[split] = set(subject_ids), photo_ids
        for name in ("hwg_metadata.csv", "measurements.csv", "subject_to_photo_map.csv"):
            content = (root / name).read_bytes()
            check_etag(content, objects[f"{split}/{name}"])
            csv_hashes[f"{split}/{name}"] = hashlib.sha256(content).hexdigest()
        for view in VIEWS:
            if {p.stem for p in (root / view).glob("*.png")} != photo_ids:
                raise ValueError(f"Missing/unmapped image in {split}/{view}")
        jobs.extend((split, row["subject_id"], row["photo_id"], view) for row in sorted(mapping, key=lambda r: (r["subject_id"], r["photo_id"])) for view in VIEWS)
    # Validate before inference and before deriving subgroup statistics.
    validate_splits({split: {"subject_ids": np.array(list(subjects[split])), "photo_ids": np.array(list(photos[split]))}
                     for split in subjects}, split_record)

    def inspect(job):
        split, subject, photo, view = job
        key = f"{split}/{view}/{photo}.png"
        content = (data_root / key).read_bytes()
        check_etag(content, objects[key])
        with Image.open(io.BytesIO(content)) as image:
            if image.mode not in ("1", "L", "P"):
                raise ValueError(f"Expected a grayscale mask, not RGB: {key}")
            quality = assess_mask(np.asarray(image.convert("L")), config["quality"])
        return {"split": split, "subject_id": subject, "photo_id": photo, "view": view,
                "relative_path": key, "sha256": hashlib.sha256(content).hexdigest(), **quality}

    summary = {}
    hashes = defaultdict(set)
    inventory = hashlib.sha256()
    audit_path = ROOT / "data/processed/bodym_phase2/quality_audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("w", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=config["workers"]) as executor:
        for index, record in enumerate(executor.map(inspect, jobs), 1):
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            inventory.update(f"{record['relative_path']}:{record['sha256']}\n".encode())
            hashes[record["split"]].add(record["sha256"])
            name = f"{record['split']}/{record['view']}"
            group = summary.setdefault(name, {"images": 0, "review_images": 0, "unusable_images": 0,
                                             "flags": Counter(), "dimensions": Counter(), "foreground_fractions": []})
            group["images"] += 1
            group["review_images"] += bool(record["flags"])
            group["unusable_images"] += not record["usable"]
            group["flags"].update(record["flags"])
            group["dimensions"][f"{record['width']}x{record['height']}"] += 1
            group["foreground_fractions"].append(record["foreground_fraction"])
            if index % 2000 == 0 or index == len(jobs):
                print(f"Audited {index:,}/{len(jobs):,} masks", flush=True)
    for group in summary.values():
        fractions = group.pop("foreground_fractions")
        group["foreground_fraction_quantiles"] = dict(zip(["min", "p05", "median", "p95", "max"],
                                                           map(float, np.quantile(fractions, [0, .05, .5, .95, 1]))))
    overlaps = {f"{left}__{right}": {"subject_ids": len(subjects[left] & subjects[right]),
                                    "photo_ids": len(photos[left] & photos[right]),
                                    "exact_image_content_hashes": len(hashes[left] & hashes[right])}
                for left, right in (("train", "testA"), ("train", "testB"), ("testA", "testB"))}
    manifest = {"dataset_id": "bodym-phase2-v1", "source": source["source"],
                "registry": "https://registry.opendata.aws/bodym/", "paper": "https://adversarialbodysim.github.io/",
                "license_review_date": "2026-10-21",
                "license_status": "Registry/paper name BY-NC 4.0 but link to BY 4.0. Non-commercial research only pending clarification.",
                "label_provenance": "14 circumferences/lengths computed from registered 3D-scan meshes, not tape/InBody labels",
                "source_manifest_sha256": sha(source_manifest), "csv_sha256": csv_hashes,
                "image_inventory_sha256": inventory.hexdigest(), "images_verified": len(jobs),
                "audit_relative_path": audit_path.relative_to(ROOT).as_posix(), "audit_sha256": sha(audit_path),
                "split_record_sha256": sha(ROOT / config["subject_split"]),
                "splits": {split: {"subjects": len(subjects[split]), "photo_pairs": len(photos[split])} for split in subjects},
                "overlaps": overlaps, "quality_config": config["quality"], "quality_summary": summary,
                "notes": ["All source CSV/image sizes and single-part ETags checked against downloaded source manifest.",
                          "Flags require review; not anatomical pose/completeness certification. No flagged test case is excluded.",
                          "testA/testB evaluated separately; never pooled as independent people."]}
    dump(ROOT / "data/manifests/bodym_phase2_v1.json", manifest)
    return manifest


def reuse_verified_audit(config):
    """Resume after a completed audit; re-hash source bytes, skip component analysis."""
    manifest = json.loads((ROOT / "data/manifests/bodym_phase2_v1.json").read_text(encoding="utf-8"))
    root = ROOT / config["data_root"]
    if sha(root / "download_manifest.json") != manifest["source_manifest_sha256"] or config["quality"] != manifest["quality_config"]:
        raise ValueError("Audit source/config differs; run a full audit")
    if sha(ROOT / config["subject_split"]) != manifest["split_record_sha256"]:
        raise ValueError("Audit split record differs")
    for key, digest in manifest["csv_sha256"].items():
        if sha(root / key) != digest:
            raise ValueError(f"CSV differs since audit: {key}")
    path = ROOT / manifest["audit_relative_path"]
    if sha(path) != manifest["audit_sha256"]:
        raise ValueError("Audit output checksum differs")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if len(records) != manifest["images_verified"]:
        raise ValueError("Audit image count differs")
    def verify(record):
        if sha(root / record["relative_path"]) != record["sha256"]:
            raise ValueError(f"Image differs since audit: {record['relative_path']}")
    with ThreadPoolExecutor(max_workers=config["workers"]) as executor:
        list(executor.map(verify, records))
    print(f"Reused mask analysis; re-verified all {len(records):,} source image hashes", flush=True)
    return manifest


@torch.inference_mode()
def infer(model, images, metadata, normalization, device, batch_size):
    if device == "cuda":
        torch.cuda.synchronize()
    start = time.perf_counter()
    output = []
    known = (metadata - normalization["metadata_mean"]) / normalization["metadata_std"]
    for index in range(0, len(images), batch_size):
        result = model(torch.as_tensor(images[index:index + batch_size], dtype=torch.float32, device=device),
                       torch.tensor(known[index:index + batch_size], dtype=torch.float32, device=device))
        output.append(result.cpu().numpy())
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    return np.concatenate(output) * normalization["target_std"] + normalization["target_mean"], elapsed


def reference_predictions(path, data):
    rows = read_csv(path)
    lookup = {(row["subject_id"], row["photo_id"]): row for row in rows}
    keys = list(zip(data["subject_ids"], data["photo_ids"]))
    if len(lookup) != len(rows) or set(lookup) != set(keys):
        raise ValueError(f"Reference prediction IDs differ: {path}")
    truth = np.array([[float(lookup[key][f"{target}_true_cm"]) for target in TARGETS] for key in keys])
    np.testing.assert_allclose(truth, data["y"], atol=2e-5, rtol=0)
    return np.array([[float(lookup[key][f"{target}_pred_cm"]) for target in TARGETS] for key in keys])


def normalize_array(pixels, config):
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    buffer.seek(0)
    return preprocess_silhouette(buffer, config)


def robustness(model, checkpoint, data, split, config, device):
    subjects, first = np.unique(data["subject_ids"], return_index=True)
    order = np.random.default_rng(config["seed"]).permutation(len(subjects))[:config["robustness"]["max_subjects_per_split"]]
    indices = first[order]
    selected = {key: data[key][indices] for key in ("images", "metadata", "y", "subject_ids", "photo_ids")}
    raw = []
    for photo in selected["photo_ids"]:
        pair = []
        for view in VIEWS:
            with Image.open(ROOT / config["data_root"] / split / view / f"{photo}.png") as image:
                pair.append(np.asarray(image.convert("L")))
        raw.append(pair)
    clean = None
    results = {}
    for transform in config["robustness"]["transforms"]:
        arrays, retained, rejected = [], [], []
        for index, pair in enumerate(raw):
            try:
                arrays.append(np.stack([normalize_array(perturb(mask, transform), checkpoint["config"]) for mask in pair]))
                retained.append(index)
            except ValueError as exc:
                rejected.append({"sample_index": index, "reason": str(exc)})
        valid = np.array(retained, dtype=int)
        if not len(valid):
            results[transform] = {"attempted_subjects": len(indices), "retained_subjects": 0, "rejected": rejected}
            continue
        images = np.stack(arrays)
        if transform in ("identity", "translate"):
            np.testing.assert_array_equal(images, selected["images"][valid])
        prediction, elapsed = infer(model, images, selected["metadata"][valid], checkpoint["normalization"], device, config["batch_size"])
        if transform == "identity":
            if len(valid) != len(indices):
                raise ValueError("Clean stress-test subset cannot contain rejected examples")
            clean = prediction
        value = score(selected["y"][valid], prediction, selected["subject_ids"][valid])
        value.update(attempted_subjects=len(indices), retained_subjects=len(valid), rejected=rejected,
                     mean_prediction_change_cm=float(np.abs(prediction - clean[valid]).mean()),
                     delta_mean_mae_cm=value["mean_mae_cm"] - score(selected["y"][valid], clean[valid], selected["subject_ids"][valid])["mean_mae_cm"],
                     inference_seconds=elapsed)
        results[transform] = value
        print(f"{split}/{transform}: MAE {value['mean_mae_cm']:.3f} cm; {len(valid)} subjects", flush=True)
    return {"selection": "Fixed-seed subject subset; lexicographically first photo per subject, no test-label selection",
            "selected_pairs_sha256": hashlib.sha256(json.dumps(selected["photo_ids"].tolist()).encode()).hexdigest(),
            "results": results}


def write_report(report, output):
    lines = ["# Phase 2 — Body Image Intelligence", "", "Checkpoint CNN giữ nguyên; không train hoặc chọn lại mô hình theo test.", "",
             "## Dataset & integrity", "", f"Đã kiểm tra {report['dataset']['images_verified']:,} ảnh silhouette và 9 CSV bằng source ETag/size.",
             "Nhãn số đo từ 3D scan/mesh; không phải phiếu InBody hay nhãn mỡ/cơ. Train/test tách người; testA/testB chung 1 ID.", "",
             "## MAE/RMSE — mỗi người trọng số bằng nhau", "",
             "| Model | Split | Chest MAE | Waist MAE | Hip MAE | Mean MAE | Chest RMSE | Waist RMSE | Hip RMSE |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for split, result in report["evaluation"].items():
        for name, value in result["models"].items():
            values = [value["mae_cm"][t] for t in TARGETS] + [value["mean_mae_cm"]] + [value["rmse_cm"][t] for t in TARGETS]
            lines.append(f"| {name} | {split} | " + " | ".join(f"{v:.3f}" for v in values) + " |")
    lines += ["", "## Quality audit", "", "| Split/view | Images | Requires review | Unusable | Flags |", "|---|---:|---:|---:|---|"]
    for name, value in report["dataset"]["quality_summary"].items():
        lines.append(f"| {name} | {value['images']} | {value['review_images']} | {value['unusable_images']} | {value['flags']} |")
    lines += ["", "Không loại ảnh bị gắn cờ khỏi đánh giá đầy đủ. Chạm mép/fragmentation chỉ là chỉ dấu kỹ thuật, không chứng minh ảnh thiếu cơ thể hay sai tư thế.",
              "", "## Subgroup errors (CNN)", "", "BMI quartiles lấy từ 1.614 người FIT; là nhóm mô tả, không phải phân loại sức khỏe.",
              "", "| Split | Group | Subjects | Mean MAE (cm) | Small group (<20) |", "|---|---|---:|---:|---|"]
    for split, result in report["evaluation"].items():
        for name, value in result["subgroups"].items():
            mae = f"{value['mean_mae_cm']:.3f}" if value["mean_mae_cm"] is not None else "N/A"
            lines.append(f"| {split} | {name} | {value['subjects']} | {mae} | {value['small_group']} |")
    lines += ["", "## Synthetic robustness (subset)", "", "Biến dạng mask gốc trước preprocessing; một cặp/người, tối đa 128 người/tập.",
              "Không tương đương đánh giá ánh sáng, camera, pose RGB hoặc thiếu trang phục phù hợp.", "",
              "| Split | Transform | Retained/attempted | Mean MAE (cm) | Delta vs clean subset (cm) |", "|---|---|---:|---:|---:|"]
    for split, result in report["robustness"].items():
        for name, value in result["results"].items():
            if value.get("retained_subjects"):
                lines.append(f"| {split} | {name} | {value['retained_subjects']}/{value['attempted_subjects']} | {value['mean_mae_cm']:.3f} | {value['delta_mean_mae_cm']:+.3f} |")
    lines += ["", "![Subgroups and robustness](evaluation.png)", "", "## Kết luận và giới hạn", "",
              "- Model chính vẫn CNN hai silhouette + chiều cao/cân nặng/giới tính được cung cấp; không phải image-only.",
              "- Ridge tham chiếu đọc từ artifact cũ, kiểm tra khóa ghép/nhãn rồi tính lại metrics; không huấn luyện lại baseline.",
              "- Không dùng chu vi mục tiêu làm đầu vào. Normalization checkpoint khớp dữ liệu train; subgroup edges chỉ dùng FIT.",
              "- Kiểm thử mask không xác nhận tư thế giải phẫu. Pose estimation/segmentation ảnh RGB chưa được triển khai hoặc benchmark.",
              "- Chưa có metadata tuổi, sắc tộc, thiết bị hay ánh sáng để đánh giá các nhóm đó; chưa có uncertainty/calibration (Phase 3).",
              "- Stress tests chỉ chẩn đoán lỗi với label cơ thể cố định, không phải độ chính xác cho người dùng thực tế; không điều chỉnh model theo test này.",
              "- Chỉ nghiên cứu phi thương mại: tên giấy phép BY-NC và link BY trên registry chưa nhất quán; cần làm rõ trước thương mại hóa.",
              "", "Nguồn: [AWS BodyM](https://registry.opendata.aws/bodym/), [trang bài báo](https://adversarialbodysim.github.io/).", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def plot_report(report, output):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for split, offset in (("testA", -.18), ("testB", .18)):
        names = [f"fit_bmi_Q{i}" for i in range(1, 5)]
        values = [report["evaluation"][split]["subgroups"][name]["mean_mae_cm"] for name in names]
        axes[0].bar(np.arange(4) + offset, [np.nan if v is None else v for v in values], .35, label=split)
        stress = report["robustness"][split]["results"]
        names = list(stress)
        axes[1].bar(np.arange(len(names)) + offset, [stress[name].get("delta_mean_mae_cm", np.nan) for name in names], .35, label=split)
    axes[0].set_xticks(range(4), ["Q1", "Q2", "Q3", "Q4"])
    axes[0].set_title("Body-size quartiles (FIT-derived); full tests")
    axes[0].set_ylabel("Subject-balanced MAE (cm)")
    axes[1].set_xticks(range(len(names)), names, rotation=30, ha="right")
    axes[1].set_title("Synthetic raw-mask stress tests; one pair/subject subset")
    axes[1].set_ylabel("MAE change vs clean subset (cm)")
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
        ax.legend()
    fig.tight_layout()
    fig.savefig(output / "evaluation.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/bodym_phase2.json")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--reuse-audit", action="store_true", help="Re-hash source files and reuse completed component analysis")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config["robustness"]["transforms"][0] != "identity":
        raise ValueError("First transform must be identity")
    output = ROOT / config["output"]
    output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(config["cpu_threads"])
    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    checkpoint_path = ROOT / config["checkpoint"]
    checkpoint_sha = sha(checkpoint_path)
    model, checkpoint = load_model(checkpoint_path, device)
    if checkpoint["preprocess_version"] != PREPROCESS_VERSION or checkpoint["phase"] != "refit_all_train":
        raise ValueError("Unexpected selected-model preprocessing/training phase")
    dataset = reuse_verified_audit(config) if args.reuse_audit else audit_dataset(config)
    data = {split: load_split(ROOT / config["data_root"], split, checkpoint["config"]) for split in ("train", "testA", "testB")}
    record = json.loads((ROOT / config["subject_split"]).read_text(encoding="utf-8"))
    validate_splits(data, record)
    normalization = fit_normalization(data["train"]["metadata"], data["train"]["y"], data["train"]["subject_ids"])
    for key in normalization:
        np.testing.assert_allclose(normalization[key], checkpoint["normalization"][key], rtol=1e-6, atol=1e-6)
    fit_mask = np.isin(data["train"]["subject_ids"], record["fit_subject_ids"])
    bins = fit_subgroup_bins(data["train"]["metadata"][fit_mask], data["train"]["subject_ids"][fit_mask])
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config,
              "checkpoint_sha256": checkpoint_sha, "checkpoint_changed": False, "preprocess_version": PREPROCESS_VERSION,
              "input_features": ["front_silhouette", "side_silhouette", "height_cm", "weight_kg", "provided_gender"],
              "targets": list(TARGETS), "dataset": dataset, "subgroup_bins": bins,
              "device": device, "versions": {"torch": torch.__version__, "numpy": np.__version__, "Pillow": PIL.__version__},
              "evaluation": {}, "robustness": {}, "reference_artifacts_sha256": {},
              "metric_definition": "Mean photo error within subject, then mean over subjects. Signed bias is prediction minus reference.",
              "latency_scope": "CNN normalization/host-device transfer/batched inference/CPU output; excludes model startup and image preprocessing"}
    canonical = json.loads((ROOT / "experiments/bodym_cnn/metrics.json").read_text(encoding="utf-8"))
    for split in ("testA", "testB"):
        current = data[split]
        prediction, elapsed = infer(model, current["images"], current["metadata"], checkpoint["normalization"], device, config["batch_size"])
        cnn_score = score(current["y"], prediction, current["subject_ids"])
        if abs(cnn_score["mean_mae_cm"] - canonical["results"][split]["mean_mae_cm"]) > 1e-4:
            raise ValueError("Checkpoint evaluation differs from selected-model report")
        models = {"selected_cnn": cnn_score}
        for name in ("metadata_ridge", "silhouette_metadata_ridge"):
            path = ROOT / "experiments/bodym_baseline" / f"{split}_{name}_predictions.csv"
            pred = reference_predictions(path, current)
            models[name] = score(current["y"], pred, current["subject_ids"])
            report["reference_artifacts_sha256"][path.relative_to(ROOT).as_posix()] = sha(path)
        report["evaluation"][split] = {"models": models, "subgroups": subgroup_scores(current["y"], prediction,
            current["subject_ids"], current["metadata"], bins, config["subgroups"]["minimum_subjects_for_stable_description"]),
            "inference_seconds": elapsed, "inference_ms_per_pair_amortized": 1000 * elapsed / len(prediction)}
        np.savez_compressed(ROOT / f"data/processed/bodym_phase2/{split}_predictions.npz", prediction=prediction,
                            y=current["y"], subject_ids=current["subject_ids"], photo_ids=current["photo_ids"])
        report["robustness"][split] = robustness(model, checkpoint, current, split, config, device)
    if sha(checkpoint_path) != checkpoint_sha:
        raise ValueError("Selected checkpoint changed during evaluation")
    dump(output / "metrics.json", report)
    plot_report(report, output)
    write_report(report, output)
    print(f"Phase 2 report: {output / 'report.md'}", flush=True)


if __name__ == "__main__":
    main()
