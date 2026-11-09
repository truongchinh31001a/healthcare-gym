"""Pure research review workflow. Does not persist or overwrite observations."""
import hashlib
import json
from copy import deepcopy
from uuid import uuid4

from .parser import now, validate_values
from .schema import FIELDS


def confirm_fields(extraction, *, reviewer_id, selected_fields, corrections=None,
                   acknowledged_flags=(), processing_consent=False):
    """Create a separate confirmation record, preserving the original draft.

    This is not authentication or a production consent store. The later API
    must obtain reviewer identity and consent from authenticated server state.
    """
    if not reviewer_id or processing_consent is not True:
        raise ValueError("Explicit reviewer identity and processing consent are required")
    selected = list(selected_fields)
    if not selected or len(set(selected)) != len(selected) or set(selected) - FIELDS.keys():
        raise ValueError("Select known, unique fields for review")
    corrections = corrections or {}
    if set(corrections) - set(selected):
        raise ValueError("Corrections must refer to selected fields")
    values = {key: extraction[key] for key in selected}
    values.update(corrections)
    if any(value is None for value in values.values()):
        raise ValueError("A missing or ambiguous value needs a manual correction")
    combined = {key: extraction[key] for key in FIELDS}
    combined.update(values)
    # All remaining consistency issues must be explicitly acknowledged.
    flags = set(validate_values(combined))
    for key in selected:
        if key not in corrections:
            flags.update(f"{key}:{flag}" for flag in extraction["field_evidence"][key]["flags"])
    flags = {flag for flag in flags if flag.split(":")[0] in selected}
    date_flags = {flag for flag in extraction["quality_flags"] if flag.startswith("measured_at:")}
    flags.update(date_flags)
    if flags - set(acknowledged_flags):
        raise ValueError(f"Review and acknowledge flags first: {sorted(flags)}")
    timestamp = now()
    return {
        "review_id": str(uuid4()), "document_id": extraction["document_id"],
        "reviewer_id": reviewer_id, "reviewed_at": timestamp,
        "extraction_sha256": hashlib.sha256(json.dumps(extraction, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "processing_consent": True, "training_consent": False,
        "observations": [{"field": key, "value": value, "unit": FIELDS[key]["unit"],
                          "source": "inbody", "provenance": "extracted", "measurement_method": "device_report",
                          "verification_status": "confirmed_by_user", "measured_at": extraction["measured_at"],
                          "quality_flags": sorted(flag for flag in flags if flag.split(":")[0] == key or flag in date_flags),
                          "recorded_at": timestamp, "model_version": extraction["model_version"]}
                         for key, value in values.items()],
        "audit": {"before": {key: extraction[key] for key in selected}, "after": deepcopy(values),
                  "acknowledged_flags": sorted(set(acknowledged_flags)), "parser_version": extraction["parser_version"]},
    }
