"""Original research-only smoke fixtures, not copies of a manufacturer's sheet."""
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from src.document_ai.schema import FIELDS, extraction_schema


def prepare(root=ROOT):
    rng = random.Random(42)
    raw = root / "data/raw/inbody_synthetic"
    annotations = root / "data/annotations/inbody_synthetic"
    manifests = root / "data/manifests"
    for path in (raw, annotations, manifests, root / "schemas"):
        path.mkdir(parents=True, exist_ok=True)
    # Pillow's embedded font makes fixture rendering independent of Windows fonts.
    title_font, font = ImageFont.load_default(size=34), ImageFont.load_default(size=26)
    samples = []
    for index in range(16):
        document_id = f"synthetic-{index:03d}"
        weight, height = round(rng.uniform(50, 105), 1), round(rng.uniform(150, 190), 1)
        fat = round(weight * rng.uniform(0.15, 0.35), 1)
        values = dict(weight_kg=weight, height_cm=height,
                      skeletal_muscle_mass_kg=round(weight * 0.4, 1), body_fat_mass_kg=fat,
                      percent_body_fat=round(100 * fat / weight, 1), total_body_water_l=round(weight * 0.55, 1),
                      ecw_tbw_ratio=round(rng.uniform(0.36, 0.4), 3),
                      basal_metabolic_rate_kcal=float(rng.randint(1200, 2100)), bmi=round(weight / (height / 100) ** 2, 1))
        lines = ["SYNTHETIC WELLNESS REPORT", "Test date: 2026-10-21"]
        for key, spec in FIELDS.items():
            # A missing field remains null; the parser must never invent it.
            if index in (7, 15) and key == "total_body_water_l":
                values[key] = None
                continue
            number = str(values[key])
            if index % 2:
                number = number.replace(".", ",")
            lines.append(f"{spec['aliases'][0]}: {number} {spec['unit']}")
        image = Image.new("RGB", (1200, 1000), "white")
        draw = ImageDraw.Draw(image)
        for row, line in enumerate(lines):
            draw.text((65, 50 + row * 66), line, font=title_font if row == 0 else font, fill="black")
        draw.text((65, 900), "Original test layout. No real person. Not a medical result.", font=font, fill="black")
        path = raw / f"{document_id}.png"
        image.save(path)
        # The footer is part of the full-page OCR transcript, not a hidden crop.
        transcript = "\n".join(lines + ["Original test layout. No real person. Not a medical result."])
        annotation = {"document_id": document_id, "subject_id": f"synthetic-subject-{index:03d}",
                      "synthetic": True, "measured_at": "2026-10-21", "values": values,
                      "transcript": transcript, "annotation_version": "synthetic-generator-0.1.0"}
        label_path = annotations / f"{document_id}.json"
        label_path.write_text(json.dumps(annotation, indent=2) + "\n", encoding="utf-8")
        samples.append({"document_id": document_id, "subject_id": annotation["subject_id"],
                        "original_document_id": document_id, "split": "dev" if index < 8 else "smoke_test",
                        "image": path.relative_to(root).as_posix(), "annotation": label_path.relative_to(root).as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "annotation_sha256": hashlib.sha256(label_path.read_bytes()).hexdigest(), "synthetic": True})
    manifest = {"dataset_id": "inbody-synthetic-smoke-v1", "seed": 42, "generator_version": "0.1.0",
                "purpose": "OCR plumbing and regression checks only; no real-world accuracy claim",
                "license": "Project-original generated fixtures; no third-party sheet/template used",
                "real_documents": 0, "samples": samples}
    (manifests / "inbody_synthetic_v1.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (root / "schemas/inbody_extraction.schema.json").write_text(json.dumps(extraction_schema(), indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    manifest = prepare()
    print(f"Prepared {len(manifest['samples'])} original synthetic documents; real documents: 0")
