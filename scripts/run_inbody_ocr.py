"""Run a local single-document extraction or a reproducible synthetic smoke test."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.document_ai.evaluation import evaluate
from src.document_ai.ocr import PaddleEngine, preprocess_document
from src.document_ai.parser import parse_lines
from src.document_ai.schema import FIELDS, extraction_schema
from src.document_ai.layout import extract_fields


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", config["experiment_id"]):
        raise ValueError("experiment_id must be a simple directory name")
    if config.get("extraction_mode", "legacy_rows") not in ("legacy_rows", "layout"):
        raise ValueError("Unknown extraction mode")
    return config


def make_engine(config):
    return PaddleEngine(device=config["device"], detection_model=config["detection_model"],
        recognition_model=config["recognition_model"], cpu_threads=config.get("cpu_threads", 4),
        use_doc_orientation_classify=config.get("use_doc_orientation_classify", False),
        use_doc_unwarping=config.get("use_doc_unwarping", False))


def load_layout(config):
    return json.loads((ROOT / config["layout_config"]).read_text(encoding="utf-8")) if config.get("layout_config") else {}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def run_document(engine, path, document_id, output, threshold, *, extraction_mode="layout", layout_config=None, template_id=None):
    from jsonschema import Draft202012Validator, FormatChecker
    start = time.perf_counter()
    prep = preprocess_document(path, output / "pages")
    ocr = engine.predict(prep["pages"])
    layout = None
    if extraction_mode == "layout":
        extraction, layout = extract_fields(ocr["tokens"], document_id, ocr["model_version"],
            pages=ocr["pages"], config=layout_config, template_id=template_id, confidence_threshold=threshold)
        dump(output / "layout.json", layout)
    elif extraction_mode == "legacy_rows":
        if template_id is not None:
            raise ValueError("Templates require layout mode")
        extraction = parse_lines(ocr["lines"], document_id, ocr["model_version"], threshold)
    else:
        raise ValueError("Unknown extraction mode")
    Draft202012Validator(extraction_schema(), format_checker=FormatChecker()).validate(extraction)
    dump(output / "ocr.json", ocr)
    dump(output / "extraction.json", extraction)
    dump(output / "provenance.json", {"source_sha256": prep["source_sha256"],
        "preprocessing_version": prep["preprocessing_version"], "model_version": ocr["model_version"],
        "extraction_mode": extraction_mode, "layout_version": layout["version"] if layout else None,
        "layout_config_sha256": hashlib.sha256(json.dumps(layout_config or {}, sort_keys=True).encode()).hexdigest(),
        "template_id": template_id, "release_status": "research_pending_review",
        "latency_seconds": time.perf_counter() - start})
    return extraction, ocr, time.perf_counter() - start


def run_benchmark(config_path=ROOT / "configs/inbody_ocr.json", engine_name="paddle"):
    if engine_name not in ("paddle", "oracle"):
        raise ValueError("Unknown benchmark engine")
    config = load_config(config_path)
    manifest = json.loads((ROOT / config["manifest"]).read_text(encoding="utf-8"))
    # This command publishes diagnostics with references. Never accept private real data here.
    if not manifest["samples"] or any(not s.get("synthetic") for s in manifest["samples"]):
        raise ValueError("Public smoke reports accept synthetic documents only")
    groups = {}
    originals = {}
    for sample in manifest["samples"]:
        for group, key in ((groups, "subject_id"), (originals, "original_document_id")):
            previous = group.setdefault(sample[key], sample["split"])
            if previous != sample["split"]:
                raise ValueError(f"Split leakage: {key}={sample[key]}")
    samples = [s for s in manifest["samples"] if s["split"] == config["split"]]
    if not samples:
        raise ValueError("No documents in requested benchmark split")
    for sample in samples:
        for path_key, hash_key in (("image", "sha256"), ("annotation", "annotation_sha256")):
            if hashlib.sha256((ROOT / sample[path_key]).read_bytes()).hexdigest() != sample[hash_key]:
                raise ValueError(f"Hash mismatch: {sample['document_id']} {path_key}")
    engine = make_engine(config) if engine_name == "paddle" else None
    pairs, latencies = [], []
    for sample in samples:
        path = ROOT / sample["image"]
        label = json.loads((ROOT / sample["annotation"]).read_text(encoding="utf-8"))
        if engine is not None:
            extraction, ocr, latency = run_document(engine, path, sample["document_id"],
                ROOT / "data/processed/inbody_ocr_runs" / config["experiment_id"] / sample["document_id"],
                config["confidence_threshold"], extraction_mode=config.get("extraction_mode", "legacy_rows"),
                layout_config=load_layout(config))
            prediction_text = "\n".join(line["text"] for line in ocr["lines"])
            latencies.append(latency)
        else:
            extraction = parse_lines([{"text": line, "confidence": None} for line in label["transcript"].splitlines()],
                                     sample["document_id"], "oracle-transcript/parser-only", config["confidence_threshold"])
            prediction_text = label["transcript"]
        pairs.append({"document_id": sample["document_id"], "reference": label["values"],
                      "prediction": extraction, "reference_text": label["transcript"], "prediction_text": prediction_text})
        print(f"{sample['document_id']}: {sum(extraction[k] is not None for k in FIELDS)}/{len(FIELDS)} fields", flush=True)
    metrics = evaluate(pairs)
    if engine is None:
        metrics.update(cer=None, wer=None, transcript_documents=0, transcript_errors=[])
    metrics.update(dataset_id=manifest["dataset_id"], split=config["split"], engine=engine_name,
                   research_only=True, release_approved=False,
                   layout_evaluated=bool(engine is not None and config.get("extraction_mode") == "layout"),
                   synthetic_only=True, real_documents=0, config=config,
                   manifest_sha256=hashlib.sha256((ROOT / config["manifest"]).read_bytes()).hexdigest(),
                   package_versions={name: importlib.metadata.version(name) for name in
                                     (["paddleocr", "paddlepaddle", "paddlex", "Pillow"] if engine else ["Pillow"])},
                   mean_latency_seconds=sum(latencies) / len(latencies) if latencies else None,
                   latency_scope="preprocessing + inference + parsing + local JSON; excludes engine/model startup",
                   correction_rate=None, correction_rate_note="No human annotation/review study yet")
    output = ROOT / "experiments" / (config["experiment_id"] + ("_oracle" if engine is None else ""))
    dump(output / "metrics.json", metrics)
    dump(output / "predictions.json", [{"document_id": p["document_id"], "values": {k: p["prediction"][k] for k in FIELDS},
          "quality_flags": p["prediction"]["quality_flags"]} for p in pairs])
    lines = [f"# InBody {engine_name} smoke result", "", "**Synthetic fixtures only — real InBody accuracy is unknown.**", "",
             f"Documents: {metrics['documents']}; split: {metrics['split']}; real documents: 0.",
             f"Field F1: {metrics['field_f1']}; document success: {metrics['document_success_rate']}.",
             f"CER: {metrics['cer']}; WER: {metrics['wer']}.", "",
             "| Field | Unit | Labeled | Paired | MAE | Exact |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for key, item in metrics["per_field"].items():
        lines.append(f"| {key} | {item['unit']} | {item['labeled']} | {item['paired']} | {item['mae']} | {item['exact']} |")
    lines += ["", "## Error analysis", "", *[f"- {e['document_id']}: {e['field']} expected {e['reference']}, got {e['prediction']}" for e in metrics["errors"]],
              *[f"- OCR text {e['document_id']}: {e['char_edits']} character edits; {e['differences']}" for e in metrics["transcript_errors"]],
              "", "Coverage is restricted to synthetic inputs recorded in this manifest; real accuracy is unknown.",
              "No real report, phone capture or clinical validation has been performed.",
              "Oracle mode bypasses OCR and must not be reported as OCR accuracy. Bounds are engineering checks, not clinical advice."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Private local image/PDF; output stays under ignored processed data")
    parser.add_argument("--engine", choices=["paddle", "oracle"], default="paddle")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/inbody_ocr.json")
    parser.add_argument("--template", help="Explicit verified template ID from the layout config; never auto-selected")
    args = parser.parse_args()
    if args.template is not None and not re.fullmatch(r"[a-zA-Z0-9_-]+", args.template):
        parser.error("Template ID must be a simple name")
    if args.input:
        if args.engine != "paddle":
            parser.error("Single-document input requires real PaddleOCR")
        import hashlib
        config = load_config(args.config)
        if args.input.stat().st_size > 30*1024*1024:
            parser.error("Document exceeds 30 MiB research limit")
        doc_id = hashlib.sha256(args.input.read_bytes()).hexdigest()[:20]
        if args.template is not None and args.template not in load_layout(config).get("templates", {}):
            parser.error("Unknown template ID")
        output = ROOT / "data/processed/inbody_private" / doc_id / config["experiment_id"] / (args.template or "generic")
        run_document(make_engine(config), args.input, doc_id, output, config["confidence_threshold"],
            extraction_mode=config.get("extraction_mode", "legacy_rows"), layout_config=load_layout(config), template_id=args.template)
        print(f"Pending user review: {output / 'extraction.json'}")
    else:
        if args.template:
            parser.error("--template is only available for single-document input")
        result = run_benchmark(args.config, args.engine)
        print(json.dumps({k: result[k] for k in ("documents", "engine", "field_f1", "document_success_rate", "cer", "wer")}))
