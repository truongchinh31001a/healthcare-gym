"""Original two-column English/Vietnamese fixtures, not manufacturer report copies."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.document_ai.schema import FIELDS


def prepare(font_path):
    font_path = Path(font_path)
    font, big = ImageFont.truetype(str(font_path), 25), ImageFont.truetype(str(font_path), 32)
    raw, labels = ROOT / "data/raw/inbody_layout_synthetic", ROOT / "data/annotations/inbody_layout_synthetic"
    raw.mkdir(parents=True, exist_ok=True); labels.mkdir(parents=True, exist_ok=True)
    samples = []
    keys = list(FIELDS)
    vietnamese = {"weight_kg": "Cân nặng", "height_cm": "Chiều cao", "skeletal_muscle_mass_kg": "Khối lượng cơ xương",
        "body_fat_mass_kg": "Khối lượng mỡ", "percent_body_fat": "Tỷ lệ mỡ cơ thể", "total_body_water_l": "Tổng lượng nước",
        "ecw_tbw_ratio": "ECW/TBW", "basal_metabolic_rate_kcal": "Chuyển hóa cơ bản", "bmi": "BMI"}
    for index in range(8):
        document_id = f"layout-synthetic-{index:03d}"
        vi = index >= 4
        image = Image.new("RGB", (1700, 1000), "white")
        draw = ImageDraw.Draw(image)
        draw.text((40, 35), "SYNTHETIC BODY DATA - ENGINEERING FIXTURE", font=big, fill="black")
        date_line = ("Ngày đo" if vi else "Test date") + ": 2026-10-21"
        draw.text((40, 110), date_line, font=font, fill="black")
        values = {"weight_kg": 70.+index, "height_cm": 170.+index, "skeletal_muscle_mass_kg": 30.+index,
            "body_fat_mass_kg": 17.+index, "percent_body_fat": round(100*(17+index)/(70+index), 1),
            "total_body_water_l": 39.+index, "ecw_tbw_ratio": .385, "basal_metabolic_rate_kcal": 1500.+10*index,
            "bmi": round((70+index)/((170+index)/100)**2, 1)}
        if index in (2, 6):
            values["total_body_water_l"] = None
        if index == 3:
            values["weight_kg"] = None  # A lone distant reference must not fill a missing result.
        boxes, transcript_rows = {}, {}
        for order, key in enumerate(keys):
            column, row = (0, order) if order < 5 else (1, order-5)
            x, value_x, ref_x = (40, 450, 720) if column == 0 else (900, 1350, 1570)
            y = 250+row*115
            label = (vietnamese[key] if vi else FIELDS[key]["aliases"][0])+":"
            draw.text((x, y), label, font=font, fill="black")
            line = label
            if values[key] is not None:
                number = f"{values[key]:g}"
                if index % 2:
                    number = number.replace(".", ",")
                value_text = number+" "+FIELDS[key]["unit"]
                draw.text((value_x, y), value_text, font=font, fill="black")
                boxes[key] = list(draw.textbbox((value_x, y), value_text, font=font))
                line += " "+value_text
            reference = "80 kg" if index == 3 and key == "weight_kg" else "Ref: 0-100"
            draw.text((ref_x, y), reference, font=font, fill="black")
            line += " "+reference
            transcript_rows.setdefault(row, []).append(line)
        footer = "Generated example only. No real person. No medical interpretation."
        draw.text((40, 930), footer, font=font, fill="black")
        transform = "none"
        if index == 6:
            image = image.filter(ImageFilter.GaussianBlur(.6)); transform = "gaussian_blur_0.6"
        if index == 5:
            path = raw / (document_id+".jpg")
            exif = Image.Exif(); exif[274] = 6
            image.rotate(90, expand=True).save(path, quality=95, exif=exif)
            transform = "raw_rotated_90_with_exif_orientation_6"
        else:
            path = raw / (document_id+".png"); image.save(path)
        annotation = {"document_id": document_id, "subject_id": document_id+"-subject", "synthetic": True,
            "measured_at": "2026-10-21", "values": values, "value_boxes": boxes, "bbox_coordinate_space": "exif_transposed_page_0",
            "transcript": "\n".join(["SYNTHETIC BODY DATA - ENGINEERING FIXTURE", date_line,
                                      *(" ".join(transcript_rows[row]) for row in sorted(transcript_rows)), footer]),
            "language": "vi" if vi else "en", "layout_family": "original-two-column", "transform": transform}
        label_path = labels / (document_id+".json")
        label_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        samples.append({"document_id": document_id, "subject_id": annotation["subject_id"], "original_document_id": document_id,
            "split": "regression", "synthetic": True, "language": annotation["language"], "layout_family": annotation["layout_family"],
            "image": path.relative_to(ROOT).as_posix(), "annotation": label_path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "annotation_sha256": hashlib.sha256(label_path.read_bytes()).hexdigest()})
    old = json.loads((ROOT / "data/manifests/inbody_synthetic_v1.json").read_text(encoding="utf-8"))
    for sample in old["samples"]:
        if sample["split"] == "smoke_test":
            samples.append({**sample, "language": "en", "layout_family": "original-simple-row"})
    manifest = {"dataset_id": "inbody-layout-regression-v1", "purpose": "Engineering regression, NOT a real or untouched clinical benchmark",
        "synthetic_only": True, "real_documents": 0, "generator_version": "0.1.0", "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
        "license": "Project-original fictitious text/layout; no manufacturer report or real identity", "samples": samples}
    destination = ROOT / "data/manifests/inbody_layout_synthetic_v1.json"
    destination.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/arial.ttf"), help="A local TrueType font with Vietnamese glyphs")
    args = parser.parse_args()
    manifest = prepare(args.font)
    print(f"Prepared {len(manifest['samples'])} synthetic regression inputs; real reports: 0")
