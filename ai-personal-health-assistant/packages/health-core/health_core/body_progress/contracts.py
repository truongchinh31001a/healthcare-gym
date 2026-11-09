"""Dashboard/planner summary contracts; raw audit is deliberately not client data."""
def summary_schemas():
    nullable_number = {"type": ["number", "null"]}
    stream = {"type": "object", "required": ["stream_id", "subject_id", "field", "provenance", "verification_band", "unit", "days", "trend"],
              "properties": {"stream_id": {"type": "string"}, "subject_id": {"type": "string"}, "field": {"type": "string"},
                             "provenance": {"enum": ["observed", "declared", "extracted", "inferred"]}, "unit": {"type": "string"},
                             "verification_band": {"type": "string"},
                             "days": {"type": "array", "items": {"type": "object", "required": ["day", "value", "observation_ids", "flags"],
                                 "properties": {"day": {"type": "string", "format": "date"}, "value": nullable_number,
                                                "observation_ids": {"type": "array", "items": {"type": "string"}}, "flags": {"type": "array", "items": {"type": "string"}}}}},
                             "trend": {"type": "object", "required": ["status", "slope_per_week", "withheld_reasons", "statistical_confidence"],
                                       "properties": {"status": {"enum": ["withheld", "descriptive_only"]}, "slope_per_week": nullable_number,
                                                      "withheld_reasons": {"type": "array", "items": {"type": "string"}}, "statistical_confidence": {"type": "null"}}}}}
    dashboard = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "BodyProgressDashboard-v1", "type": "object", "additionalProperties": False,
                 "required": ["schema_version", "subject_id", "as_of", "report_timezone", "synthetic_only", "series", "quality_summary", "interpolated_values", "clinical_interpretation"],
                 "properties": {"schema_version": {"const": "1.0.0"}, "subject_id": {"type": "string"}, "as_of": {"type": "string", "format": "date-time"},
                                "report_timezone": {"type": "string"}, "synthetic_only": {"type": "boolean"}, "series": {"type": "array", "items": stream},
                                "quality_summary": {"type": "object"}, "interpolated_values": {"const": False}, "clinical_interpretation": {"const": False}}}
    planner = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "BodyProgressPlannerContext-v1", "type": "object", "additionalProperties": False,
               "required": ["subject_id", "as_of", "facts", "needs_source_selection", "inferred_stream_ids_excluded", "missing_or_withheld_stream_ids", "plan_generation_authorized", "requires_safety_screening", "goal_changes_require_user_approval", "interpretation_limits"],
               "properties": {"subject_id": {"type": "string"}, "as_of": {"type": "string", "format": "date-time"}, "facts": {"type": "array", "items": {
                   "type": "object", "required": ["stream_id", "field", "provenance", "verification_band", "measurement_method", "trend"],
                   "properties": {"provenance": {"enum": ["observed", "extracted"]}, "verification_band": {"const": "reviewed"},
                                  "trend": {"type": "object", "required": ["status"], "properties": {"status": {"const": "descriptive_only"}}}}}},
                              "needs_source_selection": {"type": "array"}, "inferred_stream_ids_excluded": {"type": "array", "items": {"type": "string"}},
                              "missing_or_withheld_stream_ids": {"type": "array", "items": {"type": "string"}}, "plan_generation_authorized": {"const": False},
                              "requires_safety_screening": {"const": True}, "goal_changes_require_user_approval": {"const": True}, "interpretation_limits": {"type": "string"}}}
    return {"body_progress_dashboard": dashboard, "body_progress_planner_context": planner}
