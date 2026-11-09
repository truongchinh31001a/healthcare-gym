"""As-of snapshots and source-isolated descriptive trends. No medical decisions."""
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

import numpy as np
from jsonschema import Draft202012Validator
from scipy.stats import theilslopes

from .schema import FIELDS, observation_schema

REVIEWED = {"verified", "confirmed_by_user"}
INFORMATIONAL = {"date_only_precision", "unknown_protocol"}


def aware_datetime(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("An explicit UTC offset is required for timestamps")
    return result.astimezone(timezone.utc)


def reviewed(row):
    return row["provenance"] in ("observed", "extracted") and row["verification_status"] in REVIEWED


def stream_key(row):
    band = "reviewed" if reviewed(row) else row["verification_status"]
    return tuple(row.get(key) or "unknown" for key in
                 ("subject_id", "field", "provenance", "source", "measurement_method", "device_id", "device_model", "protocol_id", "model_version")) + (band,)


def normalize_observation(raw, config):
    errors = sorted(Draft202012Validator(observation_schema()).iter_errors(raw), key=lambda error: str(error.path))
    if errors:
        raise ValueError("; ".join(f"{'.'.join(map(str, e.path))}: {e.message}" for e in errors))
    row = deepcopy(raw)
    row["quality_flags"] = list(row["quality_flags"])
    recorded = aware_datetime(row["recorded_at"])
    as_of = aware_datetime(config["as_of"])
    zone = ZoneInfo(config["report_timezone"])
    row.update(canonical_value=None, canonical_unit=FIELDS[row["field"]]["unit"], day=None,
               recorded_at_utc=recorded.isoformat(), analysis_state="active", temporal_eligible=True)
    if recorded > as_of:
        row["quality_flags"].append("not_recorded_as_of")
        row["temporal_eligible"] = False
    measured = row["measured_at"]
    if measured is None:
        row["quality_flags"].append("missing_measured_at")
        row["temporal_eligible"] = False
    else:
        try:
            if len(measured) == 10:
                day = date.fromisoformat(measured)
                if row["measurement_timezone"] != config["report_timezone"]:
                    raise ValueError("Date-only observation has unknown/different timezone")
                row["quality_flags"].append("date_only_precision")
                row["day"] = day.isoformat()
                if day > as_of.astimezone(zone).date():
                    row["quality_flags"].append("future_measurement")
                    row["temporal_eligible"] = False
                if day > recorded.astimezone(zone).date():
                    row["quality_flags"].append("recorded_before_measurement")
                    row["temporal_eligible"] = False
            else:
                instant = aware_datetime(measured)
                row["day"] = instant.astimezone(zone).date().isoformat()
                if instant > as_of:
                    row["quality_flags"].append("future_measurement")
                    row["temporal_eligible"] = False
                if recorded < instant:
                    row["quality_flags"].append("recorded_before_measurement")
                    row["temporal_eligible"] = False
        except (ValueError, TypeError):
            row["quality_flags"].append("unresolved_measurement_time")
            row["temporal_eligible"] = False
            row["day"] = None
    value = row["value"]
    if value is None:
        row["quality_flags"].append("missing_value")
    elif isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("Value must be finite numeric or null")
    elif row["unit"].lower() not in FIELDS[row["field"]]["units"]:
        row["quality_flags"].append("unsupported_unit")
    else:
        row["canonical_value"] = round(float(value * FIELDS[row["field"]]["units"][row["unit"].lower()]), 9)
        low, high = FIELDS[row["field"]]["bounds"]
        if not low <= row["canonical_value"] <= high:
            row["quality_flags"].append("outside_plausibility_bounds")
    if row["device_id"] is None:
        row["quality_flags"].append("unknown_device")
    if row["protocol_id"] is None:
        row["quality_flags"].append("unknown_protocol")
    if row["provenance"] == "inferred" and row["verification_status"] != "unverified_estimate":
        raise ValueError("Inferred values cannot be promoted to verified measurements")
    if row["provenance"] == "extracted" and row["verification_status"] not in ("confirmed_by_user", "pending_user_review", "rejected"):
        raise ValueError("OCR requires explicit user review; provenance remains extracted")
    if row["provenance"] == "declared" and row["verification_status"] not in ("declared", "confirmed_by_user", "rejected"):
        raise ValueError("Self-declared values cannot claim verified measurement status")
    row["quality_flags"] = sorted(set(row["quality_flags"]))
    return row


def event_key(row):
    return stream_key(row) + (row["measurement_session_id"],)


def resolve_records(raw_rows, config):
    """Keep an immutable raw audit; analysis states never rewrite source records."""
    rows, invalid, seen = [], [], {}
    # Same ID and same payload is a duplicate copy; conflicting IDs are quarantined.
    for raw in raw_rows:
        try:
            row = normalize_observation(raw, config)
        except (ValueError, TypeError) as exc:
            invalid.append({"raw": deepcopy(raw), "reason": str(exc)})
            continue
        rows.append(row)
        if "not_recorded_as_of" in row["quality_flags"]:
            row["analysis_state"] = "not_yet_recorded"
            continue
        seen.setdefault(row["observation_id"], []).append(row)
    by_id = {}
    for identifier, copies in seen.items():
        raw_copies = [json.dumps({key: row.get(key) for key in observation_schema()["properties"]}, sort_keys=True) for row in copies]
        if len(set(raw_copies)) > 1:
            for row in copies:
                row["analysis_state"] = "quarantined_conflicting_id"
                row["quality_flags"].append("conflicting_observation_id")
        else:
            by_id[identifier] = copies[0]
            for row in copies[1:]:
                row["analysis_state"] = "duplicate_copy"
    links = defaultdict(list)
    for child in by_id.values():
        parent_id = child.get("supersedes_observation_id")
        if not parent_id or not child["temporal_eligible"]:
            continue
        parent = by_id.get(parent_id)
        audit = child.get("audit_metadata", {})
        if (parent is None or parent is child or stream_key(child)[:-1] + (child["measurement_session_id"],) != stream_key(parent)[:-1] + (parent["measurement_session_id"],)
            or not audit.get("actor_id") or not audit.get("reason")
            or aware_datetime(child["recorded_at"]) <= aware_datetime(parent["recorded_at"])):
            child["analysis_state"] = "quarantined_invalid_revision"
            child["quality_flags"].append("invalid_revision_link")
        elif reviewed(child) and child["canonical_value"] is not None:
            links[parent_id].append(child)
        else:
            child["analysis_state"] = "pending_revision"
    for parent_id, children in links.items():
        parent = by_id[parent_id]
        if len(children) > 1:
            parent["quality_flags"].append("unresolved_revision_conflict")
            for child in children:
                child["analysis_state"] = "quarantined_revision_conflict"
        elif parent["analysis_state"] == "active":
            parent["analysis_state"] = "superseded"
    # If a revision is descended from an unusable revision, do not select that branch.
    for _ in range(len(by_id)):
        changed = False
        for row in by_id.values():
            parent = by_id.get(row.get("supersedes_observation_id"))
            if row["analysis_state"] in ("active", "superseded") and parent and parent["analysis_state"].startswith("quarantined"):
                row["analysis_state"] = "quarantined_invalid_revision"
                changed = True
        if not changed:
            break
    events = defaultdict(list)
    for row in by_id.values():
        if row["analysis_state"] == "active" and row["temporal_eligible"]:
            events[event_key(row)].append(row)
    for copies in events.values():
        if len(copies) > 1:
            values = {(row["canonical_value"], row["measured_at"]) for row in copies}
            if len(values) == 1:
                for row in sorted(copies, key=lambda row: row["observation_id"])[1:]:
                    row["analysis_state"] = "duplicate_event"
            else:
                for row in copies:
                    row["quality_flags"].append("conflicting_session_values")
    for row in rows:
        row["quality_flags"] = sorted(set(row["quality_flags"]))
    return rows, invalid


def summarize_stream(rows, config):
    first = rows[0]
    as_of_day = aware_datetime(config["as_of"]).astimezone(ZoneInfo(config["report_timezone"])).date()
    start = as_of_day - timedelta(days=config["analysis_days"] - 1)
    active = [row for row in rows if row["analysis_state"] == "active" and row["temporal_eligible"] and row["day"] is not None
              and date.fromisoformat(row["day"]) >= start]
    grouped = defaultdict(list)
    for row in active:
        grouped[row["day"]].append(row)
    days = []
    for day in sorted(grouped):
        values = [row["canonical_value"] for row in grouped[day] if row["canonical_value"] is not None]
        days.append({"day": day, "value": float(np.median(values)) if values else None,
                     "observation_ids": [row["observation_id"] for row in grouped[day]],
                     "flags": sorted({flag for row in grouped[day] for flag in row["quality_flags"]})})
    points = [item for item in days if item["value"] is not None]
    rate_limit = config["engineering_max_daily_change"].get(first["field"])
    gaps = []
    for previous, current in zip(points, points[1:]):
        elapsed = (date.fromisoformat(current["day"]) - date.fromisoformat(previous["day"])).days
        if rate_limit is not None and abs(current["value"] - previous["value"]) / elapsed > rate_limit:
            current["flags"] = sorted(set(current["flags"] + ["rapid_change_review"]))
        if elapsed > config["maximum_gap_days"]:
            gaps.append({"after": previous["day"], "before": current["day"], "days_between_values": elapsed,
                         "days_without_values": elapsed - 1})
    window_start = as_of_day - timedelta(days=config["trend_days"] - 1)
    recent = [item for item in points if date.fromisoformat(item["day"]) >= window_start]
    flags = sorted({flag for item in recent for flag in item["flags"] if flag not in INFORMATIONAL})
    span = (date.fromisoformat(recent[-1]["day"]) - date.fromisoformat(recent[0]["day"])).days if recent else 0
    latest_age = (as_of_day - date.fromisoformat(points[-1]["day"])).days if points else None
    reasons = list(flags)
    if not reviewed(first):
        reasons.append("source_not_reviewed_measurement")
    if len(recent) < config["minimum_trend_days_with_values"] or span < config["minimum_trend_span_days"]:
        reasons.append("insufficient_temporal_support")
    if latest_age is None or latest_age > config["stale_after_days"]:
        reasons.append("stale_or_missing")
    if any(date.fromisoformat(gap["after"]) >= window_start for gap in gaps):
        reasons.append("large_data_gap")
    slope = None
    if not reasons:
        x = np.array([(date.fromisoformat(item["day"]) - date.fromisoformat(recent[0]["day"])).days for item in recent])
        slope = float(theilslopes([item["value"] for item in recent], x, method="joint").slope * 7)
    # Calendar-week summaries use daily medians; more same-day readings cannot dominate.
    weeks = defaultdict(list)
    for item in points:
        day = date.fromisoformat(item["day"])
        weeks[(day - timedelta(days=day.weekday())).isoformat()].append(item)
    weekly = [{"week_start": week, "median": float(np.median([item["value"] for item in items])), "days_with_values": len(items),
               "flags": sorted({flag for item in items for flag in item["flags"]})} for week, items in sorted(weeks.items())]
    windows = []
    for offset in (0, 7):
        end = as_of_day - timedelta(days=offset)
        begin = end - timedelta(days=6)
        selected = [item for item in points if begin <= date.fromisoformat(item["day"]) <= end]
        windows.append({"start": begin.isoformat(), "end": end.isoformat(), "days_with_values": len(selected),
                        "median": float(np.median([item["value"] for item in selected])) if selected else None,
                        "has_review_flags": any(set(item["flags"]) - INFORMATIONAL for item in selected)})
    current, previous = windows
    comparable = reviewed(first) and all(item["days_with_values"] >= config["minimum_week_days_with_values"] and not item["has_review_flags"] for item in windows)
    change = current["median"] - previous["median"] if comparable else None
    relative = 100 * change / previous["median"] if change is not None and previous["median"] != 0 else None
    identity = stream_key(first)
    return {"stream_id": hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20],
            **{key: first.get(key) for key in ("subject_id", "field", "provenance", "source", "measurement_method", "device_id", "device_model", "protocol_id", "model_version")},
            "verification_band": identity[-1], "unit": first["canonical_unit"], "reviewed_measurement": reviewed(first),
            "record_state_counts": {state: sum(row["analysis_state"] == state for row in rows) for state in sorted({row["analysis_state"] for row in rows})},
            "historical_audit_flags": sorted({flag for row in rows for flag in row["quality_flags"]}),
            "days": days, "weekly": weekly, "gaps": gaps, "active_observations": len(active), "days_with_values": len(points),
            "calendar_days_without_values_in_analysis_window": config["analysis_days"] - len(points),
            "latest": points[-1] if points else None, "latest_age_days": latest_age,
            "trend": {"method": "Theil-Sen on daily medians and actual elapsed days", "window_days": config["trend_days"],
                      "days_with_values": len(recent), "span_days": span, "slope_per_week": slope,
                      "status": "descriptive_only" if slope is not None else "withheld", "withheld_reasons": sorted(set(reasons)),
                      "statistical_confidence": None, "explanation": "Data-support and source checks, not a probability of health improvement. No forecast or causal conclusion."},
            "recent_week_comparison": {"current": current, "previous": previous, "change": change, "relative_percent": relative,
                                       "change_unit": "percentage_points" if first["canonical_unit"] == "%" else first["canonical_unit"]}}


def build_progress(raw_rows, config):
    """Pure deterministic snapshot. Exports never mutate measurements or goals."""
    if not 1 <= config["trend_days"] <= config["analysis_days"] <= 366:
        raise ValueError("Expected trend_days <= analysis_days <= 366")
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
        raise ValueError("Expected a JSON array of observation objects")
    aware_datetime(config["as_of"])
    ZoneInfo(config["report_timezone"])
    json.dumps(raw_rows, allow_nan=False)  # Reject non-JSON NaN/Infinity rather than hide them in quarantine output.
    rows, invalid = resolve_records(raw_rows, config)
    groups = defaultdict(list)
    for row in rows:
        if row["analysis_state"] != "not_yet_recorded":
            groups[stream_key(row)].append(row)
    series = [summarize_stream(group, config) for _, group in sorted(groups.items())]
    return {"schema_version": "1.0.0", "as_of": config["as_of"], "report_timezone": config["report_timezone"],
            "synthetic_only": bool(raw_rows) and all(raw.get("synthetic") is True for raw in raw_rows),
            "input_records": len(raw_rows), "normalized_records": len(rows), "invalid_records": invalid,
            "audit_rows": rows, "series": series,
            "limitations": ["No interpolation or forward fill; no health diagnosis, forecast or automatic goal changes.",
                            "Streams separated by subject, provenance, review band, method, source, device, protocol and model version.",
                            "Numeric changes are descriptive; engineering flags do not establish clinical thresholds."]}


def planner_context(progress, subject_id, selected_stream_ids=()):
    """Prepare facts only. Safety/goal approval remain mandatory application gates."""
    subject_streams = [stream for stream in progress["series"] if stream["subject_id"] == subject_id]
    selected = set(selected_stream_ids)
    if selected - {stream["stream_id"] for stream in subject_streams}:
        raise ValueError("Selected stream is absent or belongs to another subject")
    eligible_ids = {stream["stream_id"] for stream in subject_streams if stream["reviewed_measurement"] and stream["trend"]["status"] == "descriptive_only"}
    if selected - eligible_ids:
        raise ValueError("Selected stream is withheld or not a reviewed measurement")
    fields = defaultdict(list)
    for stream in subject_streams:
        if stream["reviewed_measurement"] and stream["trend"]["status"] == "descriptive_only":
            fields[stream["field"]].append(stream)
    facts, needs_selection = [], []
    for field, streams in sorted(fields.items()):
        explicit = [stream for stream in streams if stream["stream_id"] in selected]
        candidates = explicit if explicit else streams
        if len(candidates) != 1:
            needs_selection.append({"field": field, "candidate_stream_ids": [s["stream_id"] for s in candidates]})
            continue
        stream = candidates[0]
        facts.append({key: stream[key] for key in ("stream_id", "field", "unit", "provenance", "verification_band", "source", "measurement_method", "device_id", "device_model", "protocol_id", "model_version", "latest", "trend")})
    return {"subject_id": subject_id, "as_of": progress["as_of"], "facts": facts, "needs_source_selection": needs_selection,
            "inferred_stream_ids_excluded": [s["stream_id"] for s in subject_streams if s["provenance"] == "inferred"],
            "missing_or_withheld_stream_ids": [s["stream_id"] for s in subject_streams if s["trend"]["status"] == "withheld"],
            "plan_generation_authorized": False, "requires_safety_screening": True, "goal_changes_require_user_approval": True,
            "interpretation_limits": "Reviewed describes entry/transcription review, not clinical validation. BIA results are device estimates; no causal or clinical conclusion."}


def dashboard_payload(progress, subject_id):
    """Subject-scoped summary: never include the raw audit or other people's data."""
    known = [row for row in progress["audit_rows"] if row["subject_id"] == subject_id and row["analysis_state"] != "not_yet_recorded"]
    return {"schema_version": progress["schema_version"], "subject_id": subject_id, "as_of": progress["as_of"],
            "report_timezone": progress["report_timezone"], "synthetic_only": progress["synthetic_only"],
            "series": deepcopy([stream for stream in progress["series"] if stream["subject_id"] == subject_id]),
            "quality_summary": {"invalid_records": sum(row["raw"].get("subject_id") == subject_id for row in progress["invalid_records"]),
                                "analysis_states": {state: sum(row["analysis_state"] == state for row in known)
                                                    for state in sorted({row["analysis_state"] for row in known})}},
            "interpolated_values": False, "clinical_interpretation": False}
