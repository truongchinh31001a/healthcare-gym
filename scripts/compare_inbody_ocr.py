"""Paired 2x2 comparison: V5/V6 recognition x legacy/spatial association. Synthetic only."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import statistics
import sys
import time
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_inbody_ocr import dump, load_config, load_layout, make_engine
from src.document_ai.ocr import preprocess_document
from src.document_ai.parser import parse_lines
from src.document_ai.layout import extract_fields, VERSION
from src.document_ai.schema import FIELDS, extraction_schema
from src.document_ai.evaluation import evaluate


def overlap_covers(cell, candidate):
    x1, y1 = max(cell[0], candidate[0]), max(cell[1], candidate[1])
    x2, y2 = min(cell[2], candidate[2]), min(cell[3], candidate[3])
    return max(0, x2-x1)*max(0, y2-y1) / ((cell[2]-cell[0])*(cell[3]-cell[1])) >= .5


def compare(manifest_path, output):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = manifest["samples"]
    if not samples or any(sample.get("synthetic") is not True for sample in samples):
        raise ValueError("Public comparison accepts explicitly synthetic samples only")
    originals, subjects = {}, {}
    for sample in samples:
        for groups, key in ((originals, "original_document_id"), (subjects, "subject_id")):
            if groups.setdefault(sample[key], sample["split"]) != sample["split"]:
                raise ValueError("Split leakage")
        for source, digest in (("image", "sha256"), ("annotation", "annotation_sha256")):
            if hashlib.sha256((ROOT / sample[source]).read_bytes()).hexdigest() != sample[digest]:
                raise ValueError("Input hash mismatch")
    if len({sample["document_id"] for sample in samples}) != len(samples):
        raise ValueError("Duplicate document ID")
    validator = Draft202012Validator(extraction_schema(), format_checker=FormatChecker())
    pairs = {key: [] for key in ("v5_rows", "v5_layout", "v6_rows", "v6_layout")}
    timings, configs = {}, {}
    cache = ROOT / "data/processed/inbody_ocr_comparison_v1"
    for family, config_name in (("v5", "inbody_ocr_v5_baseline.json"), ("v6", "inbody_ocr_v6.json")):
        config = load_config(ROOT / "configs" / config_name)
        configs[family] = config
        started = time.perf_counter(); engine = make_engine(config)
        timings[family] = {"startup_seconds": time.perf_counter()-started, "documents": []}
        for sample in samples:
            document_id = sample["document_id"]
            annotation = json.loads((ROOT / sample["annotation"]).read_text(encoding="utf-8"))
            start = time.perf_counter()
            prep = preprocess_document(ROOT / sample["image"], cache / family / document_id / "pages")
            ocr = engine.predict(prep["pages"])
            inference_seconds = time.perf_counter()-start
            dump(cache / family / document_id / "ocr.json", ocr)
            timings[family]["documents"].append({"document_id": document_id, "preprocessing_and_inference_seconds": inference_seconds})
            for association in ("rows", "layout"):
                parse_start = time.perf_counter()
                if association == "rows":
                    extraction = parse_lines(ocr["lines"], document_id, ocr["model_version"], config["confidence_threshold"])
                    layout = None
                else:
                    extraction, layout = extract_fields(ocr["tokens"], document_id, ocr["model_version"], pages=ocr["pages"],
                        config=load_layout(load_config(ROOT / "configs/inbody_ocr_v6.json")), confidence_threshold=config["confidence_threshold"])
                    dump(cache / family / document_id / "layout.json", layout)
                parse_seconds = time.perf_counter()-parse_start
                validator.validate(extraction)
                dump(cache / family / document_id / (association+"_extraction.json"), extraction)
                spatial_labeled = spatial_correct = 0
                if layout:
                    for field, box in annotation.get("value_boxes", {}).items():
                        spatial_labeled += 1
                        value = extraction[field]
                        if value is not None and abs(value-annotation["values"][field]) <= 1e-6:
                            matches = [entry for entry in layout["entries"] if entry["field"] == field]
                            if len(matches) == 1 and overlap_covers(box, matches[0]["value_box"] or matches[0]["label_box"]):
                                spatial_correct += 1
                pairs[family+"_"+association].append({"document_id": document_id, "reference": annotation["values"],
                    "prediction": extraction, "reference_text": annotation["transcript"],
                    "prediction_text": "\n".join(line["text"] for line in ocr["lines"]),
                    "reference_date": annotation["measured_at"], "language": sample.get("language", "en"),
                    "layout_family": sample.get("layout_family", "simple-row"),
                    "spatial_labeled": spatial_labeled, "spatial_correct": spatial_correct,
                    "parse_seconds": parse_seconds, "total_seconds": inference_seconds+parse_seconds})
            print(f"{family} {document_id}: inference complete", flush=True)
        del engine
    results = {}
    for variant, rows in pairs.items():
        metrics = evaluate(rows)
        metrics["date_exact"] = sum(row["reference_date"] == row["prediction"]["measured_at"] for row in rows)
        metrics["date_labeled"] = sum(row["reference_date"] is not None for row in rows)
        metrics["date_exact_rate"] = metrics["date_exact"]/metrics["date_labeled"] if metrics["date_labeled"] else None
        metrics["flagged_nonnull_fields"] = sum(bool(row["prediction"]["field_evidence"][key]["flags"])
            for row in rows for key in FIELDS if row["prediction"][key] is not None)
        metrics["spatial_labeled"] = sum(row["spatial_labeled"] for row in rows)
        metrics["spatial_correct"] = sum(row["spatial_correct"] for row in rows)
        metrics["spatial_exact_recall"] = metrics["spatial_correct"]/metrics["spatial_labeled"] if metrics["spatial_labeled"] else None
        metrics["mean_seconds_excluding_model_startup"] = statistics.mean(row["total_seconds"] for row in rows)
        metrics["mean_parse_seconds"] = statistics.mean(row["parse_seconds"] for row in rows)
        metrics["subgroups"] = {f"{dimension}:{value}": evaluate([row for row in rows if row[dimension] == value])
            for dimension in ("language", "layout_family") for value in sorted({row[dimension] for row in rows})}
        results[variant] = metrics
    report = {"dataset_id": manifest["dataset_id"], "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "synthetic_only": True, "real_documents": 0, "documents": len(samples), "results": results, "configurations": configs,
        "layout_version": VERSION, "layout_config": load_layout(load_config(ROOT / "configs/inbody_ocr_v6.json")),
        "package_versions": {name: importlib.metadata.version(name) for name in ("paddleocr", "paddlepaddle", "paddlex", "Pillow")},
        "timings": timings, "design": "Each model infers once per input; both associations consume identical tokens. No template/annotation routing.",
        "correction_rate": None, "release_approved": False,
        "limitations": ["Original synthetic regression fixtures, already inspectable; not an untouched real-world test set",
            "CER/WER are computed on raw full-page OCR, not canonical field lines", "OCR scores are not calibrated field correctness probabilities",
            "No human correction-rate study, real InBody report, external layout or phone-capture benchmark", "CPU timings exclude startup and model downloads"]}
    dump(output / "metrics.json", report)
    dump(output / "predictions.json", {variant: [{"document_id": row["document_id"], "values": {key: row["prediction"][key] for key in FIELDS},
        "measured_at": row["prediction"]["measured_at"], "quality_flags": row["prediction"]["quality_flags"]} for row in rows] for variant, rows in pairs.items()})
    lines = ["# PP-OCRv5/v6 and spatial association comparison", "", "**Synthetic engineering regression only. Real report accuracy is unknown.**", "",
        f"Documents: {len(samples)}; real documents: 0. Each OCR model ran once per input; rows/layout use the same tokens.", "",
        "| Pipeline | Field precision | Field recall | Field F1 | Whole document exact | Date exact | Mean seconds |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for variant, metrics in results.items():
        lines.append(f"| {variant} | {metrics['field_precision']:.4f} | {metrics['field_recall']:.4f} | {metrics['field_f1']:.4f} | {metrics['document_success_rate']:.4f} | {metrics['date_exact_rate']:.4f} | {metrics['mean_seconds_excluding_model_startup']:.3f} |")
    lines += ["", "V6 + layout is the configured primary research candidate, not an automatic production promotion.",
        "Field exactness includes missing/extra/wrong values; null/null contributes no field true positive.",
        "Spatial recall is available only for layout variants on new fixtures with annotated value cells.",
        "Per-field unit-specific MAE, language/layout groups, OCR CER/WER and error lists are in metrics.json.",
        "", "## Limits", *["- "+item for item in report["limitations"]]]
    (output / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/inbody_layout_synthetic_v1.json")
    args = parser.parse_args()
    result = compare(args.manifest, ROOT / "experiments/inbody_ocr_comparison_v1")
    print(json.dumps({variant: values["field_f1"] for variant, values in result["results"].items()}))
