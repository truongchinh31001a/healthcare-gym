"""Build the Module 01 research notebooks once; never silently overwrite work."""
import argparse
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
SETUP = '''from pathlib import Path
import sys, json
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "Module_01_User_and_Body_Profile.md").exists())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from IPython.display import display, Markdown
'''


def write(name, cells):
    path = ROOT / "notebooks" / name
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    notebook = nbf.v4.new_notebook(cells=[nbf.v4.new_code_cell(SETUP)] + [
        nbf.v4.new_markdown_cell(text) if kind == "md" else nbf.v4.new_code_cell(text) for kind, text in cells])
    notebook.metadata.kernelspec = {"display_name": "Python (InBody OCR)", "language": "python", "name": "inbody-ocr"}
    nbf.write(notebook, path)
    return path


def create():
    paths = []
    paths.append(write("01_ocr_dataset_exploration.ipynb", [
        ("md", "# 01 — OCR dataset exploration\n\n**Research question:** Dữ liệu nào phù hợp để khảo sát OCR, và dữ liệu nào đủ để đo độ chính xác InBody?\n\nModule 01 ưu tiên Dataset → Document AI trước tích hợp ứng dụng. Seed 42; không tải phiếu thật hoặc dữ liệu bên thứ ba trong notebook này."),
        ("code", '''sources = json.loads((ROOT / "data/manifests/document_ai_sources.json").read_text(encoding="utf-8"))
rows = ["| Source | Role | Availability |", "|---|---|---|"]
for item in sources["sources"]:
    rows.append(f"| {item['id']} | {item['role']} | {item['download_status']} |")
display(Markdown("\\n".join(rows)))'''),
        ("md", "## Baseline và experiment config\n\nDùng 16 ảnh tự sinh từ layout riêng, không có người thật/logo/mẫu phiếu của hãng. 8 dev + 8 smoke_test; nhãn và transcript sinh cùng lúc. FUNSD/SROIE hỗ trợ khám phá form/receipt, không cung cấp nhãn InBody chuyên biệt. Nguồn và trạng thái quyền sử dụng ghi trong manifest."),
        ("code", '''from scripts.prepare_inbody_synthetic import prepare
manifest_path = ROOT / "data/manifests/inbody_synthetic_v1.json"
if not manifest_path.exists():
    prepare()
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
from collections import Counter
print("Dataset:", manifest["dataset_id"], "Seed:", manifest["seed"])
print("Split counts:", dict(Counter(s["split"] for s in manifest["samples"])))
print("Real documents:", manifest["real_documents"])
groups = {}
for sample in manifest["samples"]:
    assert groups.setdefault(sample["subject_id"], sample["split"]) == sample["split"]
print("Subject split check: passed")'''),
        ("code", '''from PIL import Image
import hashlib
for sample in manifest["samples"][:2]:
    path = ROOT / sample["image"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sample["sha256"]
    image = Image.open(path)
    print(sample["document_id"], image.size, sample["split"])
    display(image.resize((600, 500)))'''),
        ("md", "## Metrics / error analysis / conclusion\n\nỞ bước khảo sát chỉ báo số tài liệu, mức đầy đủ nhãn, đơn vị và leakage; chưa báo OCR accuracy. Bộ giả lập có layout sạch, ngôn ngữ tiếng Anh, cùng renderer nên không đại diện ảnh chụp điện thoại/phiếu thật. Cần thu thập phiếu được cấp quyền, gán nhãn độc lập theo guideline rồi khóa test theo người/phiếu gốc."),
        ("code", '''from src.document_ai.schema import FIELDS
missing = Counter()
for sample in manifest["samples"]:
    label = json.loads((ROOT / sample["annotation"]).read_text(encoding="utf-8"))
    missing.update(key for key in FIELDS if label["values"][key] is None)
print("Missing labels:", dict(missing))
display(Markdown("Annotation guideline: `docs/module_01/annotation_guideline.md`"))'''),
    ]))
    paths.append(write("02_inbody_preprocessing.ipynb", [
        ("md", "# 02 — InBody preprocessing\n\n**Research question:** Có thể chuẩn hóa ảnh/PDF mà giữ toàn bộ thông tin và ảnh nguồn không?\n\nDataset: synthetic v1, seed 42. Baseline: EXIF transpose → grayscale → autocontrast; chưa tự crop/deskew/denoise khi chưa có benchmark đối chứng."),
        ("code", '''from src.document_ai.ocr import preprocess_document
manifest = json.loads((ROOT / "data/manifests/inbody_synthetic_v1.json").read_text(encoding="utf-8"))
sample = manifest["samples"][0]
raw = ROOT / sample["image"]
import hashlib
before = hashlib.sha256(raw.read_bytes()).hexdigest()
result = preprocess_document(raw, ROOT / "data/processed/inbody_preprocessing_demo")
assert before == result["source_sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
print(result["preprocessing_version"], len(result["pages"]), "pages; original unchanged")
from PIL import Image
display(Image.open(result["pages"][0]).resize((600, 500)))'''),
        ("md", "## Metrics / error analysis / conclusion\n\nĐã kiểm tra không đổi file gốc, số trang và render PDF trong unit tests. Giới hạn nghiên cứu: file ≤30 MiB, ≤5 trang, ≤25 triệu pixel/trang sau render. Chưa đánh giá lợi ích cho CER/WER hoặc biến dạng phối cảnh. Cần thí nghiệm raw vs grayscale vs deskew trên phiếu thật trước lựa chọn preprocessing tốt nhất."),
    ]))
    paths.append(write("03_ocr_baseline.ipynb", [
        ("md", "# 03 — PaddleOCR + rules baseline\n\n**Research question:** OCR local → ghép hàng → parser có đọc đúng đơn vị, số thập phân và missing trên smoke fixtures không?\n\nDataset: synthetic v1; test theo subject/phiếu gốc. Baseline: PP-OCRv5 mobile CPU, PaddleOCR 3.7.0 + parser rules-0.1.0. Không dùng transcript làm đầu vào khi đo OCR."),
        ("code", '''config = json.loads((ROOT / "configs/inbody_ocr_v5_historical.json").read_text(encoding="utf-8"))
display(config)
RERUN_INFERENCE = False  # Set True explicitly for a new measured inference run.
metrics_path = ROOT / "experiments/inbody_paddle_smoke/metrics.json"
if RERUN_INFERENCE or not metrics_path.exists():
    from scripts.run_inbody_ocr import run_benchmark
    run_benchmark(config_path=ROOT / "configs/inbody_ocr_v5_historical.json")
    metrics_path = ROOT / "experiments/inbody_ocr_smoke_v1/metrics.json"
metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
assert metrics["engine"] == "paddle" and metrics["synthetic_only"]
assert metrics["config"] == config, "Cached config differs: rerun inference"
import hashlib
assert metrics["manifest_sha256"] == hashlib.sha256((ROOT / config["manifest"]).read_bytes()).hexdigest()
print("Measured packages:", metrics["package_versions"])
print({key: metrics[key] for key in ["documents", "field_f1", "document_success_rate", "cer", "wer", "mean_latency_seconds"]})'''),
        ("code", '''display(Markdown((metrics_path.parent / "report.md").read_text(encoding="utf-8")))
predictions = json.loads((metrics_path.parent / "predictions.json").read_text(encoding="utf-8"))
for prediction in predictions:
    if prediction["quality_flags"]:
        print(prediction["document_id"], prediction["quality_flags"])'''),
        ("md", "## Error analysis / conclusion\n\nMAE tính trên cặp có cả reference và prediction; phải đọc cùng coverage để tránh bỏ qua missing. Null/null không tăng field F1. CER/WER chuẩn hóa NFC, casefold và khoảng trắng, không bỏ dấu câu/đơn vị. Latency bỏ thời gian nạp engine/tải model. `oracle` chỉ kiểm parser và không có CER/WER.\n\nKết quả chỉ mô tả 8 ảnh sạch cùng renderer. Chưa có real-world benchmark, correction-rate study, layout-aware/VLM comparison hoặc ngưỡng phát hành. Mọi extraction vẫn cần người dùng kiểm tra."),
    ]))
    paths.append(write("04_inbody_information_extraction.ipynb", [
        ("md", "# 04 — Normalization, validation & review\n\n**Research question:** Dữ liệu OCR có giữ nguồn gốc và cần xác nhận trước tạo observation không?\n\nBaseline: schema versioned + kiểm tra xác định, độc lập LLM. Thí nghiệm dùng ví dụ giả lập lỗi thập phân và confidence thấp; không dùng người/phiếu thật."),
        ("code", '''from src.document_ai.parser import parse_lines
from src.document_ai.schema import extraction_schema
from jsonschema import Draft202012Validator, FormatChecker
draft = parse_lines([
    {"text": "Weight: 700 kg", "confidence": 0.72},
    {"text": "PBF: 25,5 %", "confidence": 0.99},
    {"text": "Test date: 2026-10-21", "confidence": 0.99},
], document_id="synthetic-review-demo", model_version="synthetic-error-fixture")
Draft202012Validator(extraction_schema(), format_checker=FormatChecker()).validate(draft)
print(draft["verification_status"])
print(draft["quality_flags"])'''),
        ("code", '''from src.document_ai.review import confirm_fields
try:
    confirm_fields(draft, reviewer_id="synthetic-reviewer", selected_fields=["weight_kg"], processing_consent=True)
except ValueError as exc:
    print("Blocked until reviewed:", exc)
# Demo of an explicit human correction; a future API must supply real auth/consent.
review = confirm_fields(draft, reviewer_id="synthetic-reviewer", selected_fields=["weight_kg", "percent_body_fat"],
                        corrections={"weight_kg": 70.0}, processing_consent=True)
display(review)
assert draft["weight_kg"] == 700 and draft["verification_status"] == "pending_user_review"
assert review["training_consent"] is False
assert all(o["provenance"] == "extracted" for o in review["observations"])
print("Original draft retained; separate confirmed observations created.")'''),
        ("md", "## Metrics / error analysis / conclusion\n\nUnit tests bao phủ mất đơn vị, nhãn trùng, outlier, cross-field inconsistency, confidence, consent và audit. Sửa số tạo record riêng; không biến chỉ số BIA thành ground truth, không ghi đè dữ liệu đo đã có. Chưa có UX review, DB/auth hay consent store production. Bước tiếp theo là tài liệu thật được cấp quyền và kiểm tra annotation độc lập trước tích hợp API."),
    ]))
    return paths


if __name__ == "__main__":
    for path in create():
        print(path)
