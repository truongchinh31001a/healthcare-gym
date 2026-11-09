"""Behavioral tests: provenance, no fabrication, review gates and metric bias."""
import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator, FormatChecker

from src.document_ai.evaluation import edit_distance, evaluate
from src.document_ai.ocr import group_rows, preprocess_document
from src.document_ai.parser import parse_lines, validate_values
from src.document_ai.review import confirm_fields
from src.document_ai.schema import FIELDS, extraction_schema


def parse(*texts, confidence=0.99):
    return parse_lines([{"text": text, "confidence": confidence} for text in texts], "test-doc")


class DocumentAITests(unittest.TestCase):
    def test_units_decimal_and_original_evidence(self):
        draft = parse("Weight: 150 lb", "Height: 70 in", "PBF: 25,5 %", "ECW/TBW: 0,385")
        self.assertAlmostEqual(draft["weight_kg"], 150 * 0.45359237, places=5)
        self.assertEqual(draft["height_cm"], 177.8)
        self.assertEqual(draft["percent_body_fat"], 25.5)
        self.assertEqual(draft["ecw_tbw_ratio"], 0.385)
        self.assertEqual(draft["field_evidence"]["weight_kg"]["candidates"][0]["raw_unit"], "lb")

    def test_unknown_fields_never_invent_values(self):
        draft = parse("Patient ID: 123456", "Suggested weight: 65 kg", "Weight: 68", "BMI: 22")
        self.assertTrue(all(draft[key] is None for key in FIELDS))
        self.assertIn("weight_kg:missing_or_unsupported_unit", draft["quality_flags"])

    def test_duplicate_and_reference_ranges_require_review(self):
        draft = parse("Weight: 70 kg", "Weight: 69 kg", "SMM: 30 kg (25-35)")
        self.assertIsNone(draft["weight_kg"])
        self.assertIsNone(draft["skeletal_muscle_mass_kg"])
        self.assertEqual(len(draft["field_evidence"]["weight_kg"]["candidates"]), 2)

    def test_bounds_flag_without_clamping_or_deleting(self):
        draft = parse("Weight: 900 kg")
        self.assertEqual(draft["weight_kg"], 900)
        self.assertIn("weight_kg:outside_plausibility_bounds", draft["quality_flags"])

    def test_cross_field_consistency(self):
        draft = parse("Weight: 70 kg", "BFM: 20 kg", "PBF: 50 %")
        self.assertIn("percent_body_fat:inconsistent_with_mass", draft["quality_flags"])

    def test_explicit_dates_only(self):
        self.assertEqual(parse("Test date: 2026-10-21")["measured_at"], "2026-10-21")
        self.assertIsNone(parse("Test date: 2026-02-31")["measured_at"])
        self.assertIsNone(parse("Test date: 01/02/26")["measured_at"])
        self.assertIsNone(parse("Test date: 2026-10-21", "Test date: 2026-10-20")["measured_at"])

    def test_confidence_does_not_auto_confirm(self):
        for confidence, flag in ((0.4, "low_confidence"), (None, "unknown_confidence")):
            draft = parse("Weight: 70 kg", confidence=confidence)
            self.assertIn(f"weight_kg:{flag}", draft["quality_flags"])
            self.assertEqual(draft["verification_status"], "pending_user_review")
            with self.assertRaises(ValueError):
                confirm_fields(draft, reviewer_id="user", selected_fields=["weight_kg"], processing_consent=True)

    def test_consent_and_explicit_selection_required(self):
        draft = parse("Weight: 70 kg")
        with self.assertRaises(ValueError):
            confirm_fields(draft, reviewer_id="user", selected_fields=["weight_kg"])
        with self.assertRaises(ValueError):
            confirm_fields(draft, reviewer_id="user", selected_fields=[], processing_consent=True)
        with self.assertRaises(ValueError):
            confirm_fields(draft, reviewer_id="user", selected_fields=["bmi"], processing_consent=True)

    def test_correction_creates_new_record_keeps_draft_unchanged(self):
        draft = parse("Weight: 700 kg", "Test date: 2026-10-21")
        before = copy.deepcopy(draft)
        review = confirm_fields(draft, reviewer_id="user-1", selected_fields=["weight_kg"],
                                corrections={"weight_kg": 70.0}, processing_consent=True)
        self.assertEqual(draft, before)
        self.assertEqual(review["audit"]["before"], {"weight_kg": 700})
        self.assertEqual(review["audit"]["after"], {"weight_kg": 70.0})
        self.assertFalse(review["training_consent"])
        observation = review["observations"][0]
        self.assertEqual(observation["provenance"], "extracted")
        self.assertEqual(observation["verification_status"], "confirmed_by_user")
        self.assertEqual(observation["measured_at"], "2026-10-21")

    def test_acknowledged_outlier_is_preserved(self):
        draft = parse("Weight: 900 kg")
        review = confirm_fields(draft, reviewer_id="user", selected_fields=["weight_kg"],
                                acknowledged_flags=["weight_kg:outside_plausibility_bounds"], processing_consent=True)
        self.assertEqual(review["observations"][0]["value"], 900)
        self.assertIn("weight_kg:outside_plausibility_bounds", review["observations"][0]["quality_flags"])

    def test_uncertain_date_cannot_silently_become_confirmed(self):
        draft = parse("Weight: 70 kg", "Test date: 01/02/26")
        with self.assertRaises(ValueError):
            confirm_fields(draft, reviewer_id="user", selected_fields=["weight_kg"], processing_consent=True)
        review = confirm_fields(draft, reviewer_id="user", selected_fields=["weight_kg"], processing_consent=True,
                                acknowledged_flags=["measured_at:unsupported_date_format"])
        self.assertIsNone(review["observations"][0]["measured_at"])

    def test_boolean_nan_infinite_are_invalid_numbers(self):
        for invalid in (True, float("nan"), float("inf"), "65"):
            with self.assertRaises(ValueError):
                validate_values({"weight_kg": invalid})

    def test_schema_rejects_unreviewed_confirmed_status(self):
        draft = parse("Weight (kg): 65", "SMM: 30 kg")
        validator = Draft202012Validator(extraction_schema(), format_checker=FormatChecker())
        validator.validate(draft)
        draft["verification_status"] = "confirmed_by_user"
        self.assertTrue(list(validator.iter_errors(draft)))

    def test_ocr_geometry_combines_row_not_adjacent_rows_or_pages(self):
        tokens = [{"text": text, "box": box, "page": page, "confidence": 0.9} for text, box, page in
                  [("Weight:", [10, 10, 80, 30], 0), ("65 kg", [200, 11, 250, 31], 0),
                   ("SMM: 30 kg", [10, 80, 150, 100], 0), ("BFM: 15 kg", [10, 10, 160, 30], 1)]]
        self.assertEqual([row["text"] for row in group_rows(tokens)], ["Weight: 65 kg", "SMM: 30 kg", "BFM: 15 kg"])

    def test_preprocessing_preserves_original_and_renders_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new("RGB", (300, 400), "white")
            raw = root / "test.png"
            image.save(raw)
            before = raw.read_bytes()
            result = preprocess_document(raw, root / "png")
            self.assertEqual(raw.read_bytes(), before)
            self.assertEqual(len(result["pages"]), 1)
            pdf = root / "test.pdf"
            image.save(pdf, "PDF")
            result = preprocess_document(pdf, root / "pdf")
            self.assertEqual(len(result["pages"]), 1)
            self.assertTrue(result["pages"][0].exists())

    def test_metrics_missing_values_cannot_inflate_accuracy(self):
        pairs = [{"document_id": "a", "reference": {"weight_kg": 70, "bmi": 25},
                  "prediction": {"weight_kg": 72}}]
        metrics = evaluate(pairs)
        self.assertEqual(metrics["field_f1"], 0)
        self.assertEqual(metrics["document_success_rate"], 0)
        self.assertEqual(metrics["per_field"]["weight_kg"]["mae"], 2)
        self.assertEqual(metrics["per_field"]["bmi"]["coverage"], 0)
        self.assertIsNone(metrics["per_field"]["bmi"]["mae"])
        self.assertIsNone(metrics["cer"])
        self.assertEqual(edit_distance("kitten", "sitting"), 3)


if __name__ == "__main__":
    unittest.main()
