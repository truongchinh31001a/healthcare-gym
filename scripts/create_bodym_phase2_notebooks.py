"""Populate Phase 2 notebooks; preserve every existing nonempty notebook."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
SETUP = '''from pathlib import Path
import sys, json
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "Module_01_User_and_Body_Profile.md").exists())
for path in [ROOT, ROOT / "scripts"]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from IPython.display import display, Markdown
import numpy as np
import matplotlib.pyplot as plt
'''


def write(name, question, cells):
    path = ROOT / "notebooks" / name
    if path.exists() and nbf.read(path, as_version=4).cells:
        raise FileExistsError(f"Refusing to replace nonempty notebook: {path}")
    notebook = nbf.v4.new_notebook(cells=[nbf.v4.new_markdown_cell(question), nbf.v4.new_code_cell(SETUP)] + [
        nbf.v4.new_markdown_cell(text) if kind == "md" else nbf.v4.new_code_cell(text) for kind, text in cells])
    notebook.metadata.kernelspec = {"display_name": "Python (BodyM Research)", "language": "python", "name": "bodym-research"}
    nbf.write(notebook, path)
    print(path)


def create():
    write("06_bodym_dataset_exploration.ipynb", "# 06 — BodyM dataset exploration\n\n**Research question:** Các tập BodyM có nguồn nhãn, phân bố và tính độc lập như thế nào?\n\nPhase 2 của Module 01. Seed 42; dùng dữ liệu đã tải, không đổi split và không học từ test.", [
        ("code", '''manifest = json.loads((ROOT / "data/manifests/bodym_phase2_v1.json").read_text(encoding="utf-8"))
print("Images verified:", manifest["images_verified"])
print("Label provenance:", manifest["label_provenance"])
print("License:", manifest["license_status"])
display(manifest["splits"])
display(manifest["overlaps"])'''),
        ("md", "## Dataset / baseline / experiment config\n\nBodyM cung cấp silhouette trước/nghiêng, metadata và số đo từ 3D scan/mesh. Không có ảnh RGB, keypoint, phiếu InBody hoặc nhãn mỡ/cơ. Baseline Ridge 393 features và CNN hai view đã có; phase này giữ checkpoint và bổ sung kiểm tra. Registry ghi tên BY-NC nhưng link BY: chỉ nghiên cứu phi thương mại khi chưa làm rõ."),
        ("code", '''from run_bodym_baseline import read_csv
record = json.loads((ROOT / "configs/bodym_subject_split.json").read_text(encoding="utf-8"))
fit, val = set(record["fit_subject_ids"]), set(record["validation_subject_ids"])
assert not fit & val
tables = {split: read_csv(ROOT / "data/raw/bodym" / split / "hwg_metadata.csv") for split in ("train", "testA", "testB")}
assert fit | val == {r["subject_id"] for r in tables["train"]}
for split in ("testA", "testB"):
    assert not (fit | val) & {r["subject_id"] for r in tables[split]}
print("FIT:", len(fit), "Validation:", len(val), "Train/test subject isolation passed")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for split, rows in tables.items():
    heights = np.array([float(r["height_cm"]) for r in rows])
    weights = np.array([float(r["weight_kg"]) for r in rows])
    axes[0].hist(heights, bins=np.linspace(130, 210, 25), density=True, histtype="step", label=split)
    axes[1].hist(weights / (heights / 100) ** 2, bins=np.linspace(10, 60, 26), density=True, histtype="step", label=split)
axes[0].set_xlabel("Provided height (cm)"); axes[1].set_xlabel("BMI from provided metadata")
for ax in axes:
    ax.set_ylabel("Density, one row/person"); ax.legend()
fig.tight_layout(); plt.show()'''),
        ("md", "## Metrics / error analysis / conclusion\n\n2.505 dòng người qua ba tập nhưng 2.504 ID duy nhất: testA/testB chung 1 ID, không gộp như hai mẫu người độc lập. Toàn bộ ảnh/CSV đã kiểm ETag/size, manifest lưu hash. Histogram chỉ mô tả dữ liệu, không dùng chọn model/ngưỡng. Nhóm BMI ở notebook đánh giá lấy quartile từ FIT, không mang ý nghĩa ngưỡng sức khỏe. Nguồn: [AWS](https://registry.opendata.aws/bodym/), [bài báo](https://adversarialbodysim.github.io/)."),
    ])
    write("07_body_image_preprocessing.ipynb", "# 07 — Body image preprocessing & quality\n\n**Research question:** Có thể phát hiện lỗi kỹ thuật của silhouette và chuẩn hóa hai view mà giữ tỷ lệ hình thể không?\n\nDataset BodyM; baseline binary threshold → bbox → aspect-preserving letterbox 128×96. Không thực hiện RGB segmentation hay chứng nhận pose.", [
        ("code", '''from PIL import Image
from bodym_cnn import preprocess_silhouette
from src.body_vision.quality import assess_mask
from run_bodym_baseline import read_csv
config = json.loads((ROOT / "configs/bodym_phase2.json").read_text())
cnn = json.loads((ROOT / "configs/bodym_cnn.json").read_text())
row = sorted(read_csv(ROOT / "data/raw/bodym/train/subject_to_photo_map.csv"), key=lambda r: (r["subject_id"], r["photo_id"]))[0]
fig, axes = plt.subplots(2, 2, figsize=(7, 9))
for i, view in enumerate(("mask", "mask_left")):
    path = ROOT / "data/raw/bodym/train" / view / (row["photo_id"] + ".png")
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("L"))
    quality = assess_mask(pixels, config["quality"])
    print(view, quality)
    normalized = preprocess_silhouette(path, cnn)[0]
    assert normalized.shape == (128, 96) and set(np.unique(normalized)) <= {0, 1}
    axes[i, 0].imshow(pixels, cmap="gray"); axes[i, 0].set_title(view + " raw")
    axes[i, 1].imshow(normalized, cmap="gray"); axes[i, 1].set_title("128x96 letterbox")
for ax in axes.ravel(): ax.axis("off")
fig.tight_layout(); plt.show()'''),
        ("code", '''manifest = json.loads((ROOT / "data/manifests/bodym_phase2_v1.json").read_text())
rows = ["| Split/view | Images | Requires review | Unusable |", "|---|---:|---:|---:|"]
for name, q in manifest["quality_summary"].items():
    rows.append(f"| {name} | {q['images']} | {q['review_images']} | {q['unusable_images']} |")
display(Markdown("\\n".join(rows)))'''),
        ("md", "## Experiment / metrics / error analysis\n\nQuy tắc cố định trước đánh giá: mask rỗng/full, kích thước foreground thấp, chạm khung, fragmentation, pixel không nhị phân. Cờ không tự loại ảnh khỏi metrics. Ảnh chạm khung không nhất thiết thiếu cơ thể; một silhouette sai pose vẫn có thể vượt qua mọi kiểm tra kỹ thuật.\n\nStress tests áp dụng trên mask gốc rồi đi qua chính preprocessing của checkpoint. Translation có padding phải cho cùng tensor; co/giãn biên, xoay và mất phần trên có thể làm thay đổi dự đoán. Đây không phải kiểm chứng pose/ánh sáng RGB hoặc camera thực tế."),
    ])
    write("07_body_feature_extraction.ipynb", "# 07b — Geometric feature extraction\n\n**Research question:** Đặc trưng hình học mô tả gì và có tách biệt khỏi chu vi mục tiêu không?\n\nDataset BodyM; baseline Ridge dùng hai silhouette + metadata. Không train lại hoặc đổi model đã chọn.", [
        ("code", '''from run_bodym_baseline import silhouette_features, FEATURE_NAMES, read_csv
path = ROOT / "data/raw/bodym/train"
row = sorted(read_csv(path / "subject_to_photo_map.csv"), key=lambda r: (r["subject_id"], r["photo_id"]))[0]
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
for ax, view in zip(axes, ("mask", "mask_left")):
    features = silhouette_features(path / view / (row["photo_id"] + ".png"))
    assert features.shape == (195,) and np.isfinite(features).all()
    for i, name in enumerate(("span", "occupied", "center")):
        ax.plot(np.linspace(0, 1, 64), features[i * 64:(i + 1) * 64], label=name)
    print(view, dict(zip(("aspect_ratio", "area", "fill_ratio"), features[-3:])))
    ax.set_xlabel("Normalized body height (top to bottom)"); ax.set_title(view); ax.legend()
fig.tight_layout(); plt.show()
assert len(FEATURE_NAMES) == 393
assert not {"chest", "waist", "hip"} & set(FEATURE_NAMES)
print("Features: 3 metadata + 2 x (3 profiles x 64 bins + 3 scalars) =", len(FEATURE_NAMES))'''),
        ("md", "## Metrics / error analysis / conclusion\n\nProfile span gồm cả khoảng trống giữa tay/chân; occupied chỉ đếm foreground. Center mô tả bất đối xứng. Đều chuẩn hóa theo chiều cao ảnh đã crop, không phải cm. Metadata chiều cao/cân nặng được cung cấp; chu vi ngực/eo/hông chỉ nằm ở y. Ridge dùng 393 features; CNN học encoder trực tiếp từ ảnh, không dùng bộ feature Ridge này. Xem notebook 08 và 09 cho kết quả train đã có; notebook 10 bổ sung đánh giá Phase 2."),
    ])
    write("10_model_evaluation.ipynb", "# 10 — Phase 2 model evaluation\n\n**Research question:** CNN đã chọn có sai số và giới hạn nào theo nhóm và biến dạng ảnh?\n\nBaseline: metadata Ridge, silhouette+metadata Ridge; model chính: CNN hai view. Checkpoint giữ nguyên. Protocol: split theo người; testA/testB riêng; mỗi người trọng số ngang nhau.", [
        ("code", '''report = json.loads((ROOT / "experiments/bodym_phase2/metrics.json").read_text(encoding="utf-8"))
import hashlib
assert hashlib.sha256((ROOT / report["config"]["checkpoint"]).read_bytes()).hexdigest() == report["checkpoint_sha256"]
print("Checkpoint unchanged:", not report["checkpoint_changed"])
print("Subgroup bins:", report["subgroup_bins"])
print("Packages/device:", report["versions"], report["device"])
display(Markdown((ROOT / "experiments/bodym_phase2/report.md").read_text(encoding="utf-8").replace("![Subgroups and robustness](evaluation.png)", "")))'''),
        ("code", '''from src.body_vision.analysis import score
for split in ("testA", "testB"):
    with np.load(ROOT / f"data/processed/bodym_phase2/{split}_predictions.npz") as data:
        recalculated = score(data["y"], data["prediction"], data["subject_ids"])
    expected = report["evaluation"][split]["models"]["selected_cnn"]
    assert abs(recalculated["mean_mae_cm"] - expected["mean_mae_cm"]) < 1e-10
    print(split, "independent metric recomputation passed:", recalculated["mean_mae_cm"])
from PIL import Image
display(Image.open(ROOT / "experiments/bodym_phase2/evaluation.png"))'''),
        ("md", "## Error analysis / conclusion\n\nĐọc MAE/RMSE từng chu vi, signed bias và số người mỗi nhóm trong metrics JSON. Nhóm <20 người được đánh dấu, không đủ để kết luận fairness. Nhóm BMI lấy quartiles từ 1.614 người FIT, không fit theo test. Không có tuổi/thiết bị/ánh sáng để kiểm các nhóm đó.\n\nStress subset có một cặp ảnh/người nên MAE clean subset có thể khác full test. Delta chỉ so trên đúng người còn suy luận được; số rejected và coverage được giữ. Translation phải bất biến; các biến dạng còn lại minh họa lỗi, không được dùng để tune model sau khi nhìn test.\n\nPhase 2 hoàn thành nghiên cứu silhouette trong phạm vi BodyM. RGB pose/segmentation, ảnh điện thoại được đồng ý, uncertainty/OOD/calibration và triển khai ứng dụng chưa đạt evaluation gate. Không suy luận thành phần mỡ/cơ/InBody từ silhouette."),
    ])


if __name__ == "__main__":
    create()
