"""Phase 4 synthetic study or a local private as-of progress snapshot."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date
from src.body_progress.engine import build_progress, dashboard_payload, planner_context
from src.body_progress.contracts import summary_schemas


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def load_json(path):
    def bad_constant(value):
        raise ValueError(f"Nonstandard JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=bad_constant)


def draw(progress, output):
    panels = [("synthetic-steady", "weight_kg", "Reviewed weight; separate devices"),
              ("synthetic-steady", "waist_cm", "Waist: tape vs inferred, never pooled"),
              ("synthetic-steady", "percent_body_fat", "BIA readings and confirmed OCR remain separate"),
              ("synthetic-review", "weight_kg", "Outlier retained; trend withheld")]
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    for axis, (subject, field, title) in zip(axes.flat, panels):
        streams = [s for s in progress["series"] if s["subject_id"] == subject and s["field"] == field]
        for stream in streams:
            if field == "weight_kg" and not stream["reviewed_measurement"]:
                continue
            points = [point for point in stream["days"] if point["value"] is not None]
            if not points:
                continue
            label = f"{stream['provenance']} / {stream['device_id']}"
            x, y = [date.fromisoformat(p["day"]) for p in points], [p["value"] for p in points]
            if stream["provenance"] == "extracted":
                axis.scatter(x, y, s=65, facecolors="none", edgecolors="tab:purple", label=label)
            else:
                axis.scatter(x, y, s=19, marker="x" if stream["provenance"] == "inferred" else "o", label=label)
            bad = [p for p in points if set(p["flags"]) - {"date_only_precision", "unknown_protocol"}]
            if bad:
                axis.scatter([date.fromisoformat(p["day"]) for p in bad], [p["value"] for p in bad],
                             facecolors="none", edgecolors="red", s=70, label="Review flag")
        axis.set_title(title, fontsize=10)
        axis.set_ylabel("Percent body fat (%)" if field == "percent_body_fat" else ("kg" if field == "weight_kg" else "cm"))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
    fig.suptitle("Phase 4 — original synthetic fixtures only; points, no imputation/forecast")
    fig.tight_layout()
    fig.savefig(output / "progress.png", dpi=160)
    plt.close(fig)


def synthetic_study(config):
    manifest = load_json(ROOT / "data/manifests/progress_synthetic_v1.json")
    for key, hash_key in (("input", "sha256"), ("expected", "expected_sha256")):
        if hashlib.sha256((ROOT / manifest[key]).read_bytes()).hexdigest() != manifest[hash_key]:
            raise ValueError("Synthetic fixture/annotation hash mismatch")
    rows = load_json(ROOT / manifest["input"])
    if any(row.get("synthetic") is not True for row in rows):
        raise ValueError("Public reports accept original synthetic fixtures only")
    progress = build_progress(rows, config)
    expected = load_json(ROOT / manifest["expected"])
    primary = next(stream for stream in progress["series"] if stream["subject_id"] == expected["primary_weight_subject"] and
                   stream["field"] == "weight_kg" and stream["device_id"] == expected["primary_weight_device"] and stream["provenance"] == "observed")
    if primary["trend"]["slope_per_week"] is None or abs(primary["trend"]["slope_per_week"] - expected["expected_slope_kg_per_week"]) > 1e-8:
        raise AssertionError("Known synthetic trend recovery failed")
    for subject in (expected["suspect_subject"], expected["sparse_subject"], expected["stale_subject"]):
        if any(stream["trend"]["slope_per_week"] is not None for stream in progress["series"] if stream["subject_id"] == subject):
            raise AssertionError(f"Should withhold trend for {subject}")
    subject = "synthetic-steady"
    dashboard = dashboard_payload(progress, subject)
    context = planner_context(progress, subject)
    chosen = [primary["stream_id"]] + [s["stream_id"] for s in progress["series"] if s["subject_id"] == subject and s["field"] == "percent_body_fat" and s["provenance"] == "observed"]
    selected_context = planner_context(progress, subject, chosen)
    from jsonschema import Draft202012Validator, FormatChecker
    schemas = summary_schemas()
    for name, schema in schemas.items():
        dump(ROOT / "schemas" / f"{name}.schema.json", schema)
        Draft202012Validator.check_schema(schema)
    Draft202012Validator(schemas["body_progress_dashboard"], format_checker=FormatChecker()).validate(dashboard)
    for value in (context, selected_context):
        Draft202012Validator(schemas["body_progress_planner_context"], format_checker=FormatChecker()).validate(value)
    states = dict(Counter(row["analysis_state"] for row in progress["audit_rows"]))
    metrics = {"dataset_id": manifest["dataset_id"], "input_sha256": manifest["sha256"], "synthetic_only": True,
               "real_longitudinal_subjects": 0, "records": len(rows), "series": len(progress["series"]), "analysis_states": states,
               "invalid_records": len(progress["invalid_records"]), "recovered_primary_slope_kg_per_week": primary["trend"]["slope_per_week"],
               "temporally_ineligible_records": sum(not row["temporal_eligible"] for row in progress["audit_rows"]),
               "expected_primary_slope_kg_per_week": expected["expected_slope_kg_per_week"], "trend_recovery_abs_error": abs(primary["trend"]["slope_per_week"] - expected["expected_slope_kg_per_week"]),
               "withheld_series": sum(s["trend"]["status"] == "withheld" for s in progress["series"]),
               "config": config, "medical_accuracy": None, "limitation": "Deterministic fixture checks, not longitudinal/medical validation"}
    output = ROOT / "experiments/body_progress_phase4"
    for name, value in (("progress.json", progress), ("dashboard.json", dashboard), ("planner_context.json", context),
                        ("planner_context_selected_demo.json", selected_context), ("metrics.json", metrics)):
        dump(output / name, value)
    draw(progress, output)
    lines = ["# Phase 4 — Body Progress Intelligence", "", "**Original synthetic fixtures only; real longitudinal subjects: 0.**", "",
             f"Records: {len(rows)}; subjects: {manifest['subjects']}; source-isolated streams: {len(progress['series'])}.",
             f"As-of: {config['as_of']}; reporting timezone: {config['report_timezone']}.", "",
             "## Known-trend check", "",
             f"Synthetic scale-A expected slope: {expected['expected_slope_kg_per_week']:.3f} kg/week; recovered: {primary['trend']['slope_per_week']:.3f} kg/week.",
             "This validates elapsed-day handling/unit normalization on a controlled fixture, not health effectiveness or a weight-loss recommendation.", "",
             "## Stream results", "", "| Subject | Field | Provenance | Device | Value days | 28-day slope/week | Status / reasons |",
             "|---|---|---|---|---:|---:|---|"]
    for stream in progress["series"]:
        trend = stream["trend"]
        slope = f"{trend['slope_per_week']:.3f}" if trend["slope_per_week"] is not None else "N/A"
        lines.append(f"| {stream['subject_id']} | {stream['field']} | {stream['provenance']} | {stream['device_id']} | {stream['days_with_values']} | {slope} | {trend['status']}; {', '.join(trend['withheld_reasons'])} |")
    lines += ["", "## Quality / governance", "", f"Analysis states: `{states}`.",
              "Raw audit retained. Revisions do not rewrite originals; conflicting IDs and revision branches are quarantined. Pending/future knowledge cannot replace reviewed data.",
              "Confirmed OCR stays extracted; inferred/pending/self-declared values cannot feed reviewed-measurement trends or planner facts.",
              "No interpolation/forward-fill. Calendar gaps report absence of data, not non-adherence. Percent-body-fat differences use percentage points.",
              "Source/device/protocol/model versions split streams. Multiple eligible streams require explicit source selection for planner facts.",
              "", "![Synthetic progress](progress.png)", "", "## Dashboard / Planner", "",
              "Subject-scoped dashboard payload excludes raw audit and other subjects. Planner context exports facts only, no plan or goal changes.",
              "`plan_generation_authorized=false`; safety screening, user goal approval, authenticated access and real consent store remain Phase 5 gates.",
              "", "## Limits", "",
              "BodyM has repeated photos, not verified longitudinal sessions. No dates were inferred from photo order and no real InBody history was fabricated.",
              "Rules are fixed engineering review heuristics, not clinical safety thresholds. Theil-Sen slopes are descriptive, not forecasts or validated probability of progress.",
              "Real longitudinal benchmark, device repeatability/noise assessment and user-facing integration remain unvalidated.",
              "The Phase 3 uncertainty gate remains unmet; Phase 4 does not turn inferred predictions into observed progress.",
              "", "Method reference: [SciPy Theil-Sen](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html).", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: metrics[key] for key in ("records", "series", "analysis_states", "withheld_series", "recovered_primary_slope_kg_per_week")}))
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/progress_phase4.json")
    parser.add_argument("--input", type=Path, help="Private observation JSON array; never written to public experiment reports")
    parser.add_argument("--as-of", help="Explicit timestamp with UTC offset")
    parser.add_argument("--timezone", help="Reporting IANA timezone")
    parser.add_argument("--subject-id", help="Required for private dashboard/planner summary")
    args = parser.parse_args()
    config = load_json(args.config)
    if args.as_of:
        config["as_of"] = args.as_of
    if args.timezone:
        config["report_timezone"] = args.timezone
    if args.input:
        if not args.as_of or not args.subject_id:
            parser.error("Private input requires --as-of and --subject-id")
        rows = load_json(args.input)
        progress = build_progress(rows, config)
        output = ROOT / "data/processed/progress_private" / hashlib.sha256((str(args.input.resolve()) + config["as_of"] + config["report_timezone"]).encode()).hexdigest()[:20]
        dump(output / "progress.json", progress)
        dump(output / "dashboard.json", dashboard_payload(progress, args.subject_id))
        dump(output / "planner_context.json", planner_context(progress, args.subject_id))
        print(f"Private research snapshot: {output}")
    else:
        synthetic_study(config)
