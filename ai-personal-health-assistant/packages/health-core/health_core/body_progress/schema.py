"""Versioned observation contract and units, shared with Phase 1 where possible."""
from copy import deepcopy
from health_core.document_ai.schema import FIELDS as INBODY_FIELDS

FIELDS = deepcopy(INBODY_FIELDS)
for key in ("chest_cm", "waist_cm", "hip_cm", "bicep_cm", "thigh_cm"):
    FIELDS[key] = {"unit": "cm", "bounds": [1, 300], "units": {"cm": 1, "in": 2.54}}


def observation_schema():
    nullable = {"type": ["string", "null"]}
    properties = {key: {"type": "string", "minLength": 1} for key in
                  ("observation_id", "subject_id", "measurement_session_id", "source", "measurement_method", "consent_id")}
    properties.update({key: deepcopy(nullable) for key in
                       ("measured_at", "measurement_timezone", "device_id", "device_model", "protocol_id", "model_version", "supersedes_observation_id")})
    properties.update({
        "field": {"enum": list(FIELDS)}, "value": {"type": ["number", "null"]},
        "unit": {"type": "string", "minLength": 1}, "recorded_at": {"type": "string"},
        "provenance": {"enum": ["declared", "observed", "extracted", "inferred"]},
        "verification_status": {"enum": ["declared", "verified", "confirmed_by_user", "pending_user_review", "unverified_estimate", "rejected"]},
        "synthetic": {"type": "boolean"}, "quality_flags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "audit_metadata": {"type": "object"},
    })
    required = [key for key in properties if key not in ("supersedes_observation_id", "audit_metadata")]
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "BodyProgressObservation-v1",
            "type": "object", "additionalProperties": False, "required": required, "properties": properties}
