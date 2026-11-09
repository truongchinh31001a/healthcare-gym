import copy
import unittest
import tempfile
from pathlib import Path
from PIL import Image
from jsonschema import Draft202012Validator, FormatChecker
from src.document_ai.layout import extract_fields
from src.document_ai.ocr import group_rows
from src.document_ai.parser import parse_lines
from src.document_ai.review import confirm_fields
from src.document_ai.schema import extraction_schema


def token(text, x, y=20, width=90, height=20, page=0, confidence=.99):
    return {"text": text, "box": [x, y, x+width, y+height], "page": page, "confidence": confidence}


def extract(tokens, **kwargs):
    return extract_fields(tokens, "layout-test", "provided-test-tokens", **kwargs)


class SpatialExtractionTests(unittest.TestCase):
    def test_single_document_runner_uses_layout_and_saves_review_evidence(self):
        from scripts.run_inbody_ocr import run_document
        class ProvidedTokens:
            def predict(self, pages):
                tokens = [token("Weight:", 10), token("65 kg", 140), token("Height:", 400), token("170 cm", 540)]
                return {"tokens": tokens, "lines": group_rows(tokens), "pages": [{"page": 0, "width": 800, "height": 400}],
                        "model_version": "test-provided-tokens-not-an-OCR-benchmark"}
        with tempfile.TemporaryDirectory() as directory:
            raw, output = Path(directory) / "input.png", Path(directory) / "output"
            Image.new("RGB", (800, 400), "white").save(raw)
            before = raw.read_bytes()
            result, _, _ = run_document(ProvidedTokens(), raw, "local-test", output, .85)
            self.assertEqual(raw.read_bytes(), before)
            self.assertEqual(result["weight_kg"], 65)
            self.assertEqual(result["height_cm"], 170)
            self.assertEqual(result["verification_status"], "pending_user_review")
            for name in ("layout.json", "ocr.json", "provenance.json", "extraction.json"):
                self.assertTrue((output / name).is_file())

    def test_parallel_columns_do_not_merge(self):
        tokens = [token("Weight:", 10), token("65 kg", 140), token("Height:", 400), token("170 cm", 540)]
        legacy = parse_lines(group_rows(tokens), "legacy")
        self.assertIsNone(legacy["weight_kg"])
        result, evidence = extract(tokens)
        self.assertEqual(result["weight_kg"], 65)
        self.assertEqual(result["height_cm"], 170)
        self.assertEqual(evidence["entries"][0]["value_token_ids"], [1])
        self.assertEqual(result["verification_status"], "pending_user_review")

    def test_vietnamese_split_labels_and_decimal_units(self):
        tokens = [token("Khối lượng", 10, width=100), token("cơ xương:", 120, width=95), token("31,5 kg", 250),
                  token("Tỷ lệ mỡ cơ thể:", 10, y=70, width=180), token("22,5 %", 240, y=70)]
        result, _ = extract(tokens)
        self.assertEqual(result["skeletal_muscle_mass_kg"], 31.5)
        self.assertEqual(result["percent_body_fat"], 22.5)

    def test_unit_must_be_printed_and_no_numeric_reference_guess(self):
        result, _ = extract([token("Weight:", 10), token("65", 130)])
        self.assertIsNone(result["weight_kg"])
        result, _ = extract([token("Weight:", 10), token("65 kg", 130), token("80 kg", 260)])
        self.assertIsNone(result["weight_kg"])
        self.assertIn("weight_kg:multiple_numeric_values", result["quality_flags"])

    def test_explicit_reference_heading_is_not_a_measurement(self):
        result, evidence = extract([token("Weight (kg):", 10, width=120), token("65", 160, width=40),
                                    token("Reference: 50-80", 240, width=180)])
        self.assertEqual(result["weight_kg"], 65)
        self.assertEqual(evidence["entries"][0]["excluded"][0]["reason"], "explicit_reference_column")
        missing, _ = extract([token("Weight (kg):", 10, width=120), token("Reference: 50-80", 240, width=180)])
        self.assertIsNone(missing["weight_kg"])

    def test_printed_units_inline_lb_and_duplicates(self):
        result, _ = extract([token("Weight (lb):", 10, width=120), token("150 lb", 160)])
        self.assertAlmostEqual(result["weight_kg"], round(150*.45359237, 6), places=6)
        result, _ = extract([token("Weight: 65 kg", 10, width=160), token("Weight: 70 kg", 10, y=80, width=160)])
        self.assertIsNone(result["weight_kg"])
        self.assertIn("weight_kg:multiple_candidates", result["quality_flags"])

    def test_pages_and_y_positions_never_supply_missing_neighbor_values(self):
        result, _ = extract([token("Weight:", 10), token("65 kg", 140, y=70), token("70 kg", 140, page=1)])
        self.assertIsNone(result["weight_kg"])
        result, _ = extract([token("Weight:", 10), token("65 kg", 500)])
        self.assertIsNone(result["weight_kg"])

    def test_unreviewed_and_low_confidence_stay_flagged(self):
        result, evidence = extract([token("Weight:", 10), token("65 kg", 140, confidence=.4)])
        self.assertEqual(result["weight_kg"], 65)
        self.assertIn("weight_kg:low_confidence", result["quality_flags"])
        with self.assertRaises(ValueError):
            confirm_fields(result, reviewer_id="u", selected_fields=["weight_kg"], processing_consent=True)
        self.assertEqual(evidence["entries"][0]["confidence"], .4)

    def test_review_preserves_original_source_text(self):
        raw = [token("Cân nặng:", 10, width=110), token("65,5 kg", 140)]
        before = copy.deepcopy(raw)
        result, _ = extract(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result["field_evidence"]["weight_kg"]["candidates"][0]["raw_text"], "Cân nặng: 65,5 kg")
        Draft202012Validator(extraction_schema(), format_checker=FormatChecker()).validate(result)

    def test_explicit_template_chooses_result_cell_and_does_not_synthesize_units(self):
        config = {"templates": {"test-only": {"fields": {"weight_kg": {
            "page": 0, "label_box": [0, 0, .3, .1], "value_box": [.3, 0, .5, .1]}}}}}
        pages = [{"page": 0, "width": 1000, "height": 1000}]
        raw = [token("Weight (kg):", 20, width=170), token("65", 320), token("80 kg", 600)]
        result, _ = extract(raw, pages=pages, config=config, template_id="test-only")
        self.assertEqual(result["weight_kg"], 65)
        raw[0]["text"] = "Weight:"
        result, _ = extract(raw, pages=pages, config=config, template_id="test-only")
        self.assertIsNone(result["weight_kg"])

    def test_shared_template_value_is_not_accepted_for_two_fields(self):
        config = {"templates": {"overlap": {"fields": {field: {"page": 0, "label_box": [0, 0, .3, .15],
            "value_box": [.3, 0, .5, .15]} for field in ("weight_kg", "body_fat_mass_kg")}}}}
        raw = [token("Weight:", 20), token("BFM:", 20, y=70), token("65 kg", 320, y=40)]
        result, _ = extract(raw, pages=[{"page": 0, "width": 1000, "height": 1000}], config=config, template_id="overlap")
        for field in ("weight_kg", "body_fat_mass_kg"):
            self.assertIsNone(result[field])
            self.assertIn(field+":shared_value_token", result["quality_flags"])

    def test_unknown_template_and_malformed_coordinates_fail_closed(self):
        with self.assertRaises(ValueError):
            extract([], template_id="not-registered")
        for invalid in ([0, 0, 0, 10], [0, 0, float("nan"), 20], [-1, 0, 10, 20]):
            raw = token("Weight: 65 kg", 10); raw["box"] = invalid
            with self.assertRaises(ValueError):
                extract([raw])

    def test_missing_or_ambiguous_date_stays_unresolved(self):
        result, _ = extract([token("Test date:", 10), token("01/02/26", 160)])
        self.assertIsNone(result["measured_at"])
        self.assertIn("measured_at:unsupported_date_format", result["quality_flags"])
        result, _ = extract([token("Test date:", 10), token("2026-10-21", 160)])
        self.assertEqual(result["measured_at"], "2026-10-21")


if __name__ == "__main__":
    unittest.main()
