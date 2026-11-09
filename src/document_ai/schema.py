"""Single field registry shared by extraction, validation and JSON Schema."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = json.loads((ROOT / "configs/inbody_fields.json").read_text(encoding="utf-8"))
FIELDS = REGISTRY["fields"]
SCHEMA_VERSION = REGISTRY["schema_version"]
PARSER_VERSION = "rules-0.1.0"


def extraction_schema():
    """Nullable values retain missing/invalid candidates in field_evidence."""
    properties = {
        "schema_version": {"const": SCHEMA_VERSION},
        "parser_version": {"const": PARSER_VERSION},
        "document_id": {"type": "string", "minLength": 1},
        "source": {"const": "inbody"},
        "provenance": {"const": "extracted"},
        "device_model": {"type": ["string", "null"]},
        "measured_at": {"type": ["string", "null"], "format": "date"},
        "recorded_at": {"type": "string", "format": "date-time"},
        "verification_status": {"const": "pending_user_review"},
        "model_version": {"type": "string"},
        "quality_flags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "field_evidence": {"type": "object", "additionalProperties": False,
                           "required": list(FIELDS), "properties": {
            key: {"type": "object", "additionalProperties": False,
                  "required": ["unit", "candidates", "flags"], "properties": {
                      "unit": {"const": spec["unit"]},
                      "candidates": {"type": "array", "items": {
                          "type": "object", "additionalProperties": False,
                          "required": ["raw_text", "raw_value", "raw_unit", "value", "confidence", "line_index"],
                          "properties": {
                              "raw_text": {"type": "string"}, "raw_value": {"type": ["number", "null"]},
                              "raw_unit": {"type": ["string", "null"]}, "value": {"type": ["number", "null"]},
                              "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                              "line_index": {"type": "integer", "minimum": 0}}}},
                      "flags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True}}}
            for key, spec in FIELDS.items()}},
    }
    properties.update({key: {"type": ["number", "null"], "description": spec["unit"]} for key, spec in FIELDS.items()})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "InBodyExtraction",
            "type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}
