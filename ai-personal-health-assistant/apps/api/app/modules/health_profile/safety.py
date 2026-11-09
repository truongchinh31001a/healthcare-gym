"""Deterministic wellness goal screening. Unknown answers never become negative answers."""
from datetime import date
from app.core.vault import unseal
from app.repository import singleton
from app.models import utcnow

SAFETY_FIELDS = ("pregnancy", "eating_disorder_risk", "clinician_restrictions", "acute_red_flags")


def screen_goal(db, user_id, body, dashboard):
    reasons = []
    age = None
    profile_row = singleton(db, user_id, "profile")
    context_row = singleton(db, user_id, "health_context")
    profile = unseal(profile_row.payload) if profile_row else None
    context = unseal(context_row.payload) if context_row else {}
    unknown = [key for key in SAFETY_FIELDS if context.get(key, "unknown") == "unknown"]
    positive = [key for key in SAFETY_FIELDS if context.get(key) == "yes"]
    reasons.extend("unknown:" + key for key in unknown)
    reasons.extend("professional_review:" + key for key in positive)
    if not profile:
        reasons.append("profile_required")
    else:
        birthday = date.fromisoformat(profile["birth_date"])
        today = date.today()
        age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
        if age < 20:
            reasons.append("professional_review:age_under_20")
        elif body.target_weight_kg / (profile["height_cm"] / 100) ** 2 < 18.5:
            reasons.append("professional_review:target_bmi_below_adult_screening_threshold")
    candidates = [s for s in dashboard["series"] if s["field"] == "weight_kg" and s["reviewed_measurement"]
                  and s["trend"]["status"] == "descriptive_only"]
    if body.weight_stream_id:
        candidates = [s for s in candidates if s["stream_id"] == body.weight_stream_id]
    current = None
    if len(candidates) != 1:
        reasons.append("one_eligible_weight_source_required")
    else:
        current = candidates[0]["latest"]["value"]
        if profile and age is not None and age >= 20 and current / (profile["height_cm"] / 100) ** 2 < 18.5:
            reasons.append("professional_review:current_bmi_below_adult_screening_threshold")
        if body.target_weight_kg > current:
            reasons.append("professional_review:weight_gain_goal")
        if abs(body.target_weight_kg - current) / body.weeks > 1:
            reasons.append("professional_review:requested_rate_above_wellness_limit")
    status = "needs_information" if unknown or not profile or current is None else "needs_professional_review" if reasons else "active"
    # Positive risk always takes precedence over incomplete information.
    if any(reason.startswith("professional_review:") for reason in reasons):
        status = "needs_professional_review"
    return {"rule_version": "wellness-goals-v1", "screened_at": utcnow().isoformat(), "status": status, "reasons": reasons,
            "current_weight_kg": current, "weight_stream_id": candidates[0]["stream_id"] if len(candidates) == 1 else None,
            "target_weight_kg": body.target_weight_kg, "weeks": body.weeks,
            "approved_by_user": True, "medical_clearance": False, "automatic_plan_authorized": False}
