"""Conservative same-row parser; complex tables deliberately require review."""
import math
import re
import unicodedata
from datetime import date, datetime, timezone

from .schema import FIELDS, PARSER_VERSION, SCHEMA_VERSION


def fold(text):
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_values(values):
    """Return quality flags without correcting, clamping or deleting values."""
    flags = []
    for key, spec in FIELDS.items():
        value = values.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key}: expected a finite number or null")
            low, high = spec["bounds"]
            if not low <= value <= high:
                flags.append(f"{key}:outside_plausibility_bounds")
    weight, fat, pbf = (values.get(k) for k in ("weight_kg", "body_fat_mass_kg", "percent_body_fat"))
    if weight is not None and fat is not None:
        if fat > weight:
            flags.append("body_fat_mass_kg:exceeds_weight")
        if weight > 0 and pbf is not None and abs(100 * fat / weight - pbf) > 2:
            flags.append("percent_body_fat:inconsistent_with_mass")
    return flags


def parse_lines(lines, document_id, model_version="provided-transcript", confidence_threshold=0.85):
    """lines: [{text, confidence}]. Numbers must follow an anchored field label.

    Supports explicit kg/lb, cm/in, decimal dot/comma. Thousands separators,
    reference ranges, bare-unitless values and duplicate candidates are flagged.
    Only the dimensionless ECW/TBW ratio may omit its printed unit.
    """
    if not document_id or not 0 <= confidence_threshold <= 1:
        raise ValueError("document_id and a confidence threshold in [0,1] are required")
    result = dict(schema_version=SCHEMA_VERSION, parser_version=PARSER_VERSION,
                  document_id=document_id, source="inbody", provenance="extracted",
                  device_model=None, measured_at=None, recorded_at=now(),
                  verification_status="pending_user_review", model_version=model_version,
                  quality_flags=[], field_evidence={})
    for key in FIELDS:
        result[key] = None
        result["field_evidence"][key] = {"unit": FIELDS[key]["unit"], "candidates": [], "flags": []}
    dates = []
    for index, line in enumerate(lines):
        text = line["text"]
        normalized = fold(text).strip()
        confidence = line.get("confidence")
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("OCR confidence must be in [0,1] or null")
        date_match = re.fullmatch(r"(?:test date|measurement date|ngay do)\s*[:=]?\s*(\d{4}-\d{2}-\d{2})", normalized)
        if date_match:
            try:
                dates.append(date.fromisoformat(date_match[1]).isoformat())
            except ValueError:
                result["quality_flags"].append("measured_at:invalid_date")
            if confidence is None or confidence < confidence_threshold:
                result["quality_flags"].append("measured_at:review_confidence")
        elif re.match(r"^(?:test date|measurement date|ngay do)\s*:", normalized):
            result["quality_flags"].append("measured_at:unsupported_date_format")
        for key, spec in FIELDS.items():
            # Longest aliases first, so BFM is never confused with PBF.
            aliases = sorted((fold(a) for a in spec["aliases"]), key=len, reverse=True)
            match = re.match(r"^(?:" + "|".join(re.escape(a) for a in aliases) + r")(?=$|[\s:(=])\s*[:=]?\s*(.*)$", normalized)
            if not match:
                continue
            tail = match[1].strip()
            # Accept either 'Weight (kg): 65' or 'Weight: 65 kg'.
            unit_first = re.fullmatch(r"\(([^)]+)\)\s*:?\s*([+-]?\d+(?:[.,]\d+)?)", tail)
            value_first = re.fullmatch(r"([+-]?\d+(?:[.,]\d+)?)\s*([^\d\s].*)?", tail)
            raw_value, raw_unit, value = None, None, None
            evidence = result["field_evidence"][key]
            if unit_first:
                raw_unit, number = unit_first.groups()
            elif value_first:
                number, raw_unit = value_first.groups()
            else:
                evidence["flags"].append("ambiguous_value")
                number = None
            if number is not None:
                raw_value = float(number.replace(",", "."))
                raw_unit = raw_unit.strip().lower() if raw_unit else None
                if raw_unit is None and spec["unit"] == "ratio":
                    value = raw_value
                elif raw_unit in spec["units"]:
                    value = round(raw_value * spec["units"][raw_unit], 6)
                else:
                    evidence["flags"].append("missing_or_unsupported_unit")
            if confidence is None:
                evidence["flags"].append("unknown_confidence")
            elif confidence < confidence_threshold:
                evidence["flags"].append("low_confidence")
            evidence["candidates"].append(dict(raw_text=text, raw_value=raw_value, raw_unit=raw_unit,
                                                 value=value, confidence=confidence, line_index=index))
    if len(dates) == 1:
        result["measured_at"] = dates[0]
    elif len(dates) > 1:
        result["quality_flags"].append("measured_at:multiple_candidates")
    for key, evidence in result["field_evidence"].items():
        candidates = evidence["candidates"]
        if len(candidates) == 1:
            result[key] = candidates[0]["value"]
        elif len(candidates) > 1:
            evidence["flags"].append("multiple_candidates")
        else:
            evidence["flags"].append("missing")
        evidence["flags"] = sorted(set(evidence["flags"]))
        result["quality_flags"].extend(f"{key}:{flag}" for flag in evidence["flags"])
    result["quality_flags"] = sorted(set(result["quality_flags"] + validate_values(result)))
    return result
