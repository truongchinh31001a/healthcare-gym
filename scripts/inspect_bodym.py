"""Check BodyM tables, image mappings, and split isolation using Python only."""

from collections import Counter
import csv
from datetime import datetime, timezone
import itertools
import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data/raw/bodym"


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main():
    summary = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "splits": {}}
    subject_sets = {}
    photo_sets = {}
    for split in ("train", "testA", "testB"):
        root = DATA_ROOT / split
        metadata = read_csv(root / "hwg_metadata.csv")
        measurements = read_csv(root / "measurements.csv")
        mapping = read_csv(root / "subject_to_photo_map.csv")
        subjects = {row["subject_id"] for row in metadata}
        photos = {row["photo_id"] for row in mapping}
        if len(subjects) != len(metadata):
            raise ValueError(f"{split}: duplicate metadata subject IDs")
        if len({row['subject_id'] for row in measurements}) != len(measurements):
            raise ValueError(f"{split}: duplicate measurement subject IDs")
        if subjects != {row["subject_id"] for row in measurements}:
            raise ValueError(f"{split}: metadata and measurement subject IDs differ")
        if subjects != {row["subject_id"] for row in mapping}:
            raise ValueError(f"{split}: metadata and photo-map subject IDs differ")
        if len(photos) != len(mapping):
            raise ValueError(f"{split}: duplicate photo IDs")
        for row in metadata:
            for field in ("height_cm", "weight_kg"):
                value = float(row[field])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{split}: invalid {field}")
        for row in measurements:
            for field, raw_value in row.items():
                if field != "subject_id":
                    value = float(raw_value)
                    if not math.isfinite(value) or value <= 0:
                        raise ValueError(f"{split}: invalid {field}")
        counts = {}
        for directory in ("mask", "mask_left"):
            image_ids = {path.stem for path in (root / directory).glob("*.png")}
            if image_ids != photos:
                raise ValueError(f"{split}/{directory}: missing or unmapped images")
            counts[directory] = len(image_ids)
        subject_sets[split] = subjects
        photo_sets[split] = photos
        summary["splits"][split] = {
            "subjects": len(subjects),
            "photo_pairs": len(photos),
            "png_images": sum(counts.values()),
            "images_by_directory": counts,
            "gender_counts": dict(Counter(row["gender"] for row in metadata)),
            "measurement_columns": [key for key in measurements[0] if key != "subject_id"],
        }
    overlaps = {}
    for left, right in itertools.combinations(subject_sets, 2):
        subject_overlap = len(subject_sets[left] & subject_sets[right])
        photo_overlap = len(photo_sets[left] & photo_sets[right])
        overlaps[f"{left}__{right}"] = {
            "shared_subject_ids": subject_overlap,
            "shared_photo_ids": photo_overlap,
        }
        if subject_overlap and "train" in (left, right):
            raise ValueError(f"Subject leakage between {left} and {right}")
        if photo_overlap:
            raise ValueError(f"Photo leakage between {left} and {right}")
    summary["totals"] = {
        field: sum(split[field] for split in summary["splits"].values())
        for field in ("photo_pairs", "png_images")
    }
    summary["totals"]["subject_entries"] = sum(len(ids) for ids in subject_sets.values())
    summary["totals"]["unique_subject_ids"] = len(set.union(*subject_sets.values()))
    summary["split_overlaps"] = overlaps
    summary["checks"] = {
        "tables_and_image_mappings": "passed",
        "positive_finite_measurements": "passed",
        "train_subject_isolation_from_tests": "passed",
        "photo_split_isolation": "passed",
    }
    if overlaps["testA__testB"]["shared_subject_ids"]:
        summary["notes"] = [
            "The original testA and testB tables share subject IDs; keep test results separate. "
            "Subject entries across splits therefore differ from unique subject IDs."
        ]
    report = PROJECT_ROOT / "data/annotations/bodym_summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
