"""Temporal/source boundaries and known outcomes, not implementation-mirroring tests."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest

from scripts.prepare_progress_synthetic import observation
from src.body_progress.engine import build_progress, dashboard_payload, planner_context, normalize_observation
from src.body_progress.adapters import observations_from_review, observations_from_prediction

ROOT = Path(__file__).resolve().parents[1]


class BodyProgressTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "configs/progress_phase4.json").read_text())

    def series(self, subject="a", device="scale-A", provenance="observed", status="verified"):
        return [observation(f"{subject}-{device}-{provenance}-{day}", subject, day, "weight_kg", 80 - .04 * day,
                            device=device, provenance=provenance, status=status) for day in range(28, 56)]

    def test_actual_elapsed_days_and_unit_conversion(self):
        rows = [observation(str(day), "a", day, "weight_kg", 80 - .04 * day) for day in (30, 37, 44, 55)]
        rows[1].update(value=rows[1]["value"] / .45359237, unit="lb")
        progress = build_progress(rows, self.config)
        self.assertAlmostEqual(progress["series"][0]["trend"]["slope_per_week"], -.28, places=8)
        self.assertEqual(progress["series"][0]["unit"], "kg")

    def test_timezone_alignment_uses_measurement_not_upload_date(self):
        row = observation("time", "a", 55, "weight_kg", 80)
        row.update(measured_at="2026-10-20T23:30:00Z", recorded_at="2026-10-21T12:00:00Z")
        normalized = normalize_observation(row, self.config)
        self.assertEqual(normalized["day"], "2026-10-21")

    def test_date_only_never_gets_fabricated_time_or_timezone(self):
        row = observation("date", "a", 55, "weight_kg", 80)
        row["measured_at"] = "2026-10-21"
        normalized = normalize_observation(row, self.config)
        self.assertEqual(normalized["measured_at"], "2026-10-21")
        self.assertIn("date_only_precision", normalized["quality_flags"])
        row["measurement_timezone"] = None
        self.assertFalse(normalize_observation(row, self.config)["temporal_eligible"])
        row["measured_at"] = None
        normalized = normalize_observation(row, self.config)
        self.assertIsNone(normalized["day"])

    def test_no_naive_timestamp_or_future_knowledge(self):
        rows = self.series()
        base = build_progress(rows, self.config)
        future = observation("future", "a", 65, "weight_kg", 300)
        late = deepcopy(rows[-1])
        late.update(observation_id="late", recorded_at="2026-10-30T00:00:00Z", value=10)
        result = build_progress(rows + [future, late], self.config)
        self.assertEqual(result["series"][0]["latest"], base["series"][0]["latest"])
        self.assertEqual(result["series"][0]["trend"], base["series"][0]["trend"])
        row = deepcopy(rows[0])
        row["recorded_at"] = "2026-10-21T10:00:00"
        self.assertEqual(len(build_progress([row], self.config)["invalid_records"]), 1)

    def test_sources_devices_and_model_versions_never_pool(self):
        rows = self.series() + self.series(device="scale-B")
        ml = self.series(device="camera", provenance="inferred", status="unverified_estimate")
        for index, row in enumerate(ml):
            row["model_version"] = "v1" if index < 14 else "v2"
        progress = build_progress(rows + ml, self.config)
        self.assertEqual(len(progress["series"]), 4)
        self.assertTrue(all(s["trend"]["slope_per_week"] is None for s in progress["series"] if s["provenance"] == "inferred"))
        context = planner_context(progress, "a")
        self.assertFalse(context["facts"])
        self.assertEqual(context["needs_source_selection"][0]["field"], "weight_kg")
        primary = next(s for s in progress["series"] if s["device_id"] == "scale-A")
        self.assertEqual(len(planner_context(progress, "a", [primary["stream_id"]])["facts"]), 1)

    def test_pending_ocr_and_ml_cannot_change_reviewed_trend(self):
        rows = self.series()
        expected = build_progress(rows, self.config)["series"][0]["trend"]["slope_per_week"]
        pending = self.series(device="BIA", provenance="extracted", status="pending_user_review")
        for row in pending:
            row["value"] = 200
        result = build_progress(rows + pending, self.config)
        actual = next(s for s in result["series"] if s["provenance"] == "observed")
        self.assertEqual(actual["trend"]["slope_per_week"], expected)
        self.assertTrue(all(f["provenance"] != "extracted" for f in planner_context(result, "a")["facts"]))
        inferred = deepcopy(rows[0]); inferred.update(provenance="inferred", verification_status="confirmed_by_user")
        self.assertEqual(len(build_progress([inferred], self.config)["invalid_records"]), 1)

    def test_duplicate_photos_or_records_do_not_dominate_day_or_week(self):
        rows = self.series()
        baseline = build_progress(rows, self.config)["series"][0]
        repeated = build_progress(rows + [deepcopy(rows[0])] * 100, self.config)["series"][0]
        self.assertEqual(baseline["weekly"], repeated["weekly"])
        self.assertEqual(baseline["trend"], repeated["trend"])

    def test_daily_then_weekly_median_prevents_frequency_bias(self):
        rows = [observation("d1", "a", 53, "weight_kg", 70), observation("d2", "a", 54, "weight_kg", 80), observation("d3", "a", 55, "weight_kg", 90)]
        for i in range(20):
            copy = deepcopy(rows[0]); copy.update(observation_id=f"extra-{i}", measurement_session_id=f"extra-session-{i}")
            rows.append(copy)
        progress = build_progress(rows, self.config)
        self.assertEqual(progress["series"][0]["weekly"][-1]["median"], 80)

    def test_outlier_is_visible_but_trend_is_withheld(self):
        rows = self.series()
        rows[-3]["value"] = 200
        progress = build_progress(rows, self.config)
        stream = progress["series"][0]
        self.assertIsNone(stream["trend"]["slope_per_week"])
        self.assertIn("rapid_change_review", stream["trend"]["withheld_reasons"])
        self.assertEqual(max(day["value"] for day in stream["days"]), 200)
        self.assertEqual(len(progress["audit_rows"]), len(rows))

    def test_gaps_sparse_and_stale_do_not_generate_filled_trends(self):
        rows = [observation("one", "a", 28, "weight_kg", 80), observation("two", "a", 55, "weight_kg", 78)]
        stream = build_progress(rows, self.config)["series"][0]
        self.assertEqual(len(stream["days"]), 2)
        self.assertEqual(stream["gaps"][0]["days_without_values"], 26)
        self.assertIsNone(stream["trend"]["slope_per_week"])
        stale = build_progress([observation(str(i), "a", i, "weight_kg", 80) for i in range(10)], self.config)["series"][0]
        self.assertIn("stale_or_missing", stale["trend"]["withheld_reasons"])

    def test_correction_retains_original_and_cannot_cross_sources(self):
        rows = self.series()
        original = deepcopy(rows[-1])
        child = deepcopy(original)
        child.update(observation_id="correction", value=77, supersedes_observation_id=original["observation_id"],
                     recorded_at="2026-10-21T10:00:00+07:00", audit_metadata={"actor_id": "reviewer", "reason": "fix entry"})
        before = deepcopy(rows)
        result = build_progress(rows + [child], self.config)
        self.assertEqual(rows, before)
        self.assertEqual(next(r for r in result["audit_rows"] if r["observation_id"] == original["observation_id"])["analysis_state"], "superseded")
        malicious = deepcopy(child); malicious.update(observation_id="ml", provenance="inferred", verification_status="unverified_estimate")
        result = build_progress(rows + [malicious], self.config)
        self.assertEqual(next(s for s in result["series"] if s["provenance"] == "observed")["latest"]["value"], original["value"])

    def test_forked_revisions_do_not_choose_latest_automatically(self):
        rows = self.series()
        parent = rows[-1]
        a = deepcopy(parent); a.update(observation_id="revision-a", value=77, supersedes_observation_id=parent["observation_id"],
                                       recorded_at="2026-10-21T08:00:00+07:00", audit_metadata={"actor_id": "a", "reason": "edit"})
        b = deepcopy(a); b.update(observation_id="revision-b", value=90, recorded_at="2026-10-21T09:00:00+07:00")
        stream = build_progress(rows + [a, b], self.config)["series"][0]
        self.assertEqual(stream["latest"]["value"], parent["value"])
        self.assertIn("unresolved_revision_conflict", stream["trend"]["withheld_reasons"])

    def test_conflicting_ids_quarantined_and_invalid_numeric_units_preserved(self):
        row = observation("same", "a", 55, "weight_kg", 70)
        result = build_progress([row, {**row, "value": 90}], self.config)
        self.assertEqual(len(result["series"][0]["days"]), 0)
        self.assertTrue(all(r["analysis_state"] == "quarantined_conflicting_id" for r in result["audit_rows"]))
        bad_unit = {**row, "unit": "stone"}
        normalized = normalize_observation(bad_unit, self.config)
        self.assertEqual(normalized["value"], 70)
        self.assertIsNone(normalized["canonical_value"])
        with self.assertRaises(ValueError):
            build_progress([{**row, "value": float("nan")}], self.config)

    def test_percent_change_uses_percentage_points_and_zero_is_not_missing(self):
        rows = [observation(str(day), "a", day, "percent_body_fat", 0 if day <= 49 else 1, device="BIA", method="device_report") for day in range(43, 56)]
        change = build_progress(rows, self.config)["series"][0]["recent_week_comparison"]
        self.assertEqual(change["change"], 1)
        self.assertIsNone(change["relative_percent"])
        self.assertEqual(change["change_unit"], "percentage_points")

    def test_subject_scoping_and_planner_safety_gate(self):
        progress = build_progress(self.series("a") + self.series("b"), self.config)
        dashboard = dashboard_payload(progress, "a")
        self.assertTrue(all(s["subject_id"] == "a" for s in dashboard["series"]))
        self.assertNotIn("audit_rows", dashboard)
        context = planner_context(progress, "a")
        self.assertFalse(context["plan_generation_authorized"])
        self.assertTrue(context["requires_safety_screening"])
        other = next(s for s in progress["series"] if s["subject_id"] == "b")
        with self.assertRaises(ValueError):
            planner_context(progress, "a", [other["stream_id"]])

    def test_review_adapter_retains_extracted_provenance_and_unknown_date(self):
        review = {"review_id": "r1", "reviewer_id": "reviewer", "processing_consent": True, "observations": [
            {"field": "weight_kg", "value": 70, "unit": "kg", "measured_at": None, "recorded_at": "2026-10-20T12:00:00Z",
             "source": "inbody", "provenance": "extracted", "measurement_method": "device_report", "verification_status": "confirmed_by_user", "quality_flags": [], "model_version": "ocr-v1"}]}
        rows = observations_from_review(review, subject_id="a", session_id="session", device_id="BIA", device_model="BIA", measurement_timezone="Asia/Bangkok", protocol_id="morning", consent_id="consent")
        result = build_progress(rows, self.config)
        self.assertEqual(result["series"][0]["provenance"], "extracted")
        self.assertFalse(result["series"][0]["days"])

    def test_ml_adapter_never_uses_inference_time_as_capture_time(self):
        prediction = {"provenance": "inferred", "verification_status": "unverified_estimate", "recorded_at": "2026-10-21T10:00:00Z",
                      "checkpoint_sha256": "research-model", "nominal_coverage": .9, "ood": {"flagged": False}, "quality_flags": {"front": [], "side": []},
                      "estimates": {"waist": {"point_cm": 80, "per_target_interval_cm": [75, 85], "joint_interval_cm": [73, 87]}}}
        rows = observations_from_prediction(prediction, prediction_id="p1", subject_id="a", session_id="s1", capture_measured_at=None,
                                             measurement_timezone="Asia/Bangkok", device_id="camera", protocol_id="capture", consent_id="consent")
        result = build_progress(rows, self.config)
        self.assertEqual(result["series"][0]["provenance"], "inferred")
        self.assertIsNone(result["audit_rows"][0]["day"])
        self.assertIn("research_ml_uncertainty_gate_not_met", result["audit_rows"][0]["quality_flags"])
        self.assertFalse(planner_context(result, "a")["facts"])

    def test_late_duplicate_id_and_future_model_do_not_leak_into_past_snapshot(self):
        rows = self.series()
        baseline = build_progress(rows, self.config)
        late_conflict = deepcopy(rows[-1])
        late_conflict.update(recorded_at="2026-10-30T10:00:00Z", value=10)
        future_model = deepcopy(late_conflict)
        future_model.update(observation_id="new-model", provenance="inferred", verification_status="unverified_estimate", model_version="not-yet-existing-model")
        result = build_progress(rows + [late_conflict, future_model], self.config)
        self.assertEqual(baseline["series"], result["series"])
        self.assertEqual(dashboard_payload(baseline, "a"), dashboard_payload(result, "a"))
        self.assertEqual(sum(row["analysis_state"] == "not_yet_recorded" for row in result["audit_rows"]), 2)


if __name__ == "__main__":
    unittest.main()
