"""Original longitudinal fixtures; never reinterpret BodyM photo order as dates."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.body_progress.schema import observation_schema


def observation(identifier, subject, day, field, value, *, provenance="observed", status="verified", device="scale-A", method="digital_scale", source="manual_measurement", version=None):
    measured = datetime.fromisoformat("2026-08-27T07:00:00+07:00") + timedelta(days=day)
    return {"observation_id": identifier, "subject_id": subject, "measurement_session_id": f"{subject}:{device}:{day}",
            "field": field, "value": value, "unit": "kg" if field == "weight_kg" or field.endswith("_mass_kg") else ("%" if field == "percent_body_fat" else "cm"),
            "measured_at": measured.isoformat(), "recorded_at": (measured + timedelta(minutes=5)).isoformat(),
            "measurement_timezone": "Asia/Bangkok", "provenance": provenance, "source": source, "measurement_method": method,
            "verification_status": status, "device_id": device, "device_model": device, "protocol_id": "synthetic-morning",
            "model_version": version, "consent_id": "synthetic-processing-only", "synthetic": True, "quality_flags": []}


def prepare(root=ROOT):
    rows = []
    for day in range(56):
        weight = round(80 - .04 * day, 3)
        row = observation(f"steady-weight-{day:03d}", "synthetic-steady", day, "weight_kg", weight)
        if day % 2:
            row.update(value=weight / .45359237, unit="lb")
        rows.append(row)
        if day >= 41:
            rows.append(observation(f"steady-scaleB-{day:03d}", "synthetic-steady", day, "weight_kg", weight + 2, device="scale-B"))
        if day % 4 == 0 or day == 55:
            rows.append(observation(f"steady-waist-{day:03d}", "synthetic-steady", day, "waist_cm", round(95 - .07 * day, 3), device="tape-A", method="tape_measure"))
            rows.append(observation(f"ml-waist-{day:03d}", "synthetic-steady", day, "waist_cm", round(100 - .1 * day, 3),
                                    device="camera-A", method="two_view_silhouette_regression", source="synthetic_ml_fixture",
                                    provenance="inferred", status="unverified_estimate", version="synthetic-ml-v1"))
        if day % 7 == 0 or day == 55:
            rows.append(observation(f"steady-smm-{day:03d}", "synthetic-steady", day, "skeletal_muscle_mass_kg", round(30 + .005 * day, 3), device="BIA-A", method="bioimpedance_device"))
            pbf = round(25 - .02 * day, 3)
            rows.append(observation(f"steady-pbf-{day:03d}", "synthetic-steady", day, "percent_body_fat", pbf, device="BIA-A", method="bioimpedance_device"))
            ocr = observation(f"ocr-pbf-{day:03d}", "synthetic-steady", day, "percent_body_fat", pbf, device="BIA-A", method="device_report", source="inbody",
                              provenance="extracted", status="confirmed_by_user", version="synthetic-parser-v1")
            ocr["measured_at"] = ocr["measured_at"][:10]  # Date precision stays explicit, never invent an instant.
            rows.append(ocr)
            rows.append(observation(f"pending-weight-{day:03d}", "synthetic-steady", day, "weight_kg", weight + 10, device="BIA-A", method="device_report", source="inbody",
                                    provenance="extracted", status="pending_user_review", version="synthetic-parser-v1"))
    # An explicitly reviewed correction keeps the wrong original in audit.
    parent = next(row for row in rows if row["observation_id"] == "steady-weight-010")
    corrected = deepcopy(parent)
    parent["value"] = 900
    corrected.update(observation_id="steady-weight-010-revision", supersedes_observation_id=parent["observation_id"],
                     recorded_at="2026-09-06T08:00:00+07:00", audit_metadata={"actor_id": "synthetic-reviewer", "reason": "synthetic transcription correction"})
    rows.append(corrected)
    rows.append(deepcopy(rows[0]))  # Same-ID duplicate copy.
    duplicate = deepcopy(rows[1])
    duplicate["observation_id"] = "same-event-new-id"
    rows.append(duplicate)
    missing_time = deepcopy(next(row for row in rows if row["observation_id"].startswith("pending-weight")))
    missing_time.update(observation_id="ocr-unknown-time", measurement_session_id="unknown-time-session", measured_at=None)
    rows.append(missing_time)
    late = deepcopy(corrected)
    late.update(observation_id="late-revision", supersedes_observation_id=corrected["observation_id"], recorded_at="2026-10-25T09:00:00+07:00", value=10)
    rows.append(late)
    rows.append(observation("future-reading", "synthetic-steady", 64, "weight_kg", 20))
    for day in range(56):
        if 20 <= day <= 40:
            continue
        value = 90 - .02 * day + (12 if day == 50 else 0)
        rows.append(observation(f"review-weight-{day:03d}", "synthetic-review", day, "weight_kg", round(value, 3)))
    for day in (0, 24, 55):
        rows.append(observation(f"sparse-weight-{day:03d}", "synthetic-sparse", day, "weight_kg", 70 + .01 * day))
    for day in range(10):
        rows.append(observation(f"stale-weight-{day:03d}", "synthetic-stale", day, "weight_kg", 65))
    conflict = observation("conflicting-id", "synthetic-conflict", 50, "weight_kg", 75)
    rows += [conflict, {**conflict, "value": 85}]
    raw = root / "data/raw/progress_synthetic/observations.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    expected = {"primary_weight_subject": "synthetic-steady", "primary_weight_device": "scale-A", "expected_slope_kg_per_week": -.28,
                "suspect_subject": "synthetic-review", "sparse_subject": "synthetic-sparse", "stale_subject": "synthetic-stale",
                "expected_corruption_policy": "Keep raw originals, review outliers, quarantine conflicting IDs, ignore future knowledge at as_of",
                "real_longitudinal_validation": False}
    path = root / "data/annotations/progress_synthetic/expected.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    manifest = {"dataset_id": "body-progress-synthetic-v1", "generator_version": "1.0.0", "seed": 42,
                "records": len(rows), "subjects": len({row["subject_id"] for row in rows}), "real_subjects": 0,
                "input": raw.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                "expected": path.relative_to(root).as_posix(), "expected_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "origin": "Original deterministic fixtures, no real person or copied clinical record",
                "purpose": "Known-trend and adversarial behavior checks only; not medical or real-world longitudinal validation"}
    manifest_path = root / "data/manifests/progress_synthetic_v1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    schema_path = root / "schemas/body_progress_observation.schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(observation_schema(), indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
