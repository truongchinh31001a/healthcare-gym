"""Explicit adapters: review never changes provenance; capture time is not upload time."""


def observations_from_review(review, *, subject_id, session_id, device_id, device_model,
                             measurement_timezone, protocol_id, consent_id, synthetic=False):
    if review.get("processing_consent") is not True:
        raise ValueError("Review must have processing consent evidence")
    result = []
    for observation in review["observations"]:
        if observation["provenance"] != "extracted" or observation["verification_status"] != "confirmed_by_user":
            raise ValueError("Only explicitly reviewed OCR observations accepted")
        result.append({"observation_id": f"{review['review_id']}:{observation['field']}", "subject_id": subject_id,
                       "measurement_session_id": session_id, "field": observation["field"], "value": observation["value"],
                       "unit": observation["unit"], "measured_at": observation["measured_at"], "recorded_at": observation["recorded_at"],
                       "measurement_timezone": measurement_timezone, "source": observation["source"], "provenance": "extracted",
                       "measurement_method": observation["measurement_method"], "verification_status": "confirmed_by_user",
                       "device_id": device_id, "device_model": device_model, "protocol_id": protocol_id,
                       "model_version": observation["model_version"], "consent_id": consent_id, "synthetic": synthetic,
                       "quality_flags": observation["quality_flags"], "audit_metadata": {"review_id": review["review_id"], "reviewer_id": review["reviewer_id"]}})
    return result


def observations_from_prediction(prediction, *, prediction_id, subject_id, session_id, capture_measured_at,
                                 measurement_timezone, device_id, protocol_id, consent_id, synthetic=False):
    if prediction.get("provenance") != "inferred" or prediction.get("verification_status") != "unverified_estimate":
        raise ValueError("Expected Phase 3 inferred/unverified research result")
    flags = ["research_ml_uncertainty_gate_not_met"]
    if prediction["ood"]["flagged"]:
        flags.append("ml_novelty_flag")
    for view, reasons in prediction["quality_flags"].items():
        flags.extend(f"{view}:{reason}" for reason in reasons)
    return [{"observation_id": f"{prediction_id}:{field}", "subject_id": subject_id, "measurement_session_id": session_id,
             "field": field + "_cm", "value": value["point_cm"], "unit": "cm", "measured_at": capture_measured_at,
             "recorded_at": prediction["recorded_at"], "measurement_timezone": measurement_timezone,
             "source": "bodym_phase3_research", "provenance": "inferred", "measurement_method": "two_view_silhouette_regression",
             "verification_status": "unverified_estimate", "device_id": device_id, "device_model": None,
             "protocol_id": protocol_id, "model_version": prediction["checkpoint_sha256"], "consent_id": consent_id,
             "synthetic": synthetic, "quality_flags": sorted(set(flags)),
             "audit_metadata": {"prediction_id": prediction_id, "per_target_interval_cm": value["per_target_interval_cm"],
                                "joint_interval_cm": value["joint_interval_cm"], "nominal_coverage": prediction["nominal_coverage"]}}
            for field, value in prediction["estimates"].items()]
