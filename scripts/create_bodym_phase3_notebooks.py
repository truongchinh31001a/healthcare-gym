"""Create Phase 3 research notebooks without replacing completed Phase 2 work."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
SETUP = '''from pathlib import Path
import sys, json
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "Module_01_User_and_Body_Profile.md").exists())
for path in [ROOT, ROOT / "scripts"]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
import numpy as np
from IPython.display import display, Markdown
report = json.loads((ROOT / "experiments/bodym_phase3/metrics.json").read_text(encoding="utf-8"))
'''


def write(name, question, cells):
    path = ROOT / "notebooks" / name
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    notebook = nbf.v4.new_notebook(cells=[nbf.v4.new_markdown_cell(question), nbf.v4.new_code_cell(SETUP)] + [
        nbf.v4.new_markdown_cell(value) if kind == "md" else nbf.v4.new_code_cell(value) for kind, value in cells])
    notebook.metadata.kernelspec = {"display_name": "Python (BodyM Research)", "language": "python", "name": "bodym-research"}
    nbf.write(notebook, path)
    print(path)


def create():
    write("11_multimodal_ablation.ipynb", "# 11 — Multimodal ablation\n\n**Research question:** Metadata, ảnh và fusion đóng góp thế nào khi được huấn luyện lại trên cùng người?\n\nDataset: BodyM silhouettes + provided metadata. Seed 42; proper-fit/tuning/calibration/test tách theo người. Default CNN giữ nguyên.", [
        ("code", '''split = json.loads((ROOT / "experiments/bodym_phase3/subject_split.json").read_text())
groups = [set(split[key]) for key in ["proper_fit_subject_ids", "tuning_subject_ids", "calibration_subject_ids"]]
assert all(not groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3))
print("Subject counts:", report["subject_counts"], "Refit:", report["refit_subjects"])
print("Historical reuse:", report["historical_reuse"])
display(report["training_config"])'''),
        ("md", "## Baseline / experiment config\n\nBa mạng được train từ đầu: MLP metadata; shared CNN hai view không metadata; shared CNN + metadata fusion. Bỏ nhánh khỏi kiến trúc, không che input của model fusion đã train. Chọn epoch bằng 404 tuning subjects rồi refit 1.695 người; calibration 323 người chưa tham gia các bước mới này. Chỉ một seed; không coi đây là causal/statistical proof."),
        ("code", '''rows = ["| Variant | Params | Epoch | Tune MAE | TestA MAE | TestB MAE |", "|---|---:|---:|---:|---:|---:|"]
for name, result in report["results"].items():
    rows.append(f"| {name} | {result['parameters']} | {result['selection']['selected_epoch']} | {result['selection']['tuning_mean_mae_cm']:.3f} | {result['tests']['testA']['point']['mean_mae_cm']:.3f} | {result['tests']['testB']['point']['mean_mae_cm']:.3f} |")
display(Markdown("\\n".join(rows)))
from src.body_vision.analysis import score
for name, result in report["results"].items():
    for test in ["testA", "testB"]:
        with np.load(ROOT / f"data/processed/bodym_phase3/{name}/{test}_predictions.npz") as data:
            recomputed = score(data["y"], data["prediction"], data["subject_ids"])
        assert abs(recomputed["mean_mae_cm"] - result["tests"][test]["point"]["mean_mae_cm"]) < 1e-10
print("Independent point metric checks passed")'''),
        ("code", '''from PIL import Image
display(Image.open(ROOT / "experiments/bodym_phase3/comparison.png"))
import hashlib
default = json.loads((ROOT / "configs/default_model.json").read_text())
assert hashlib.sha256((ROOT / default["checkpoint"]).read_bytes()).hexdigest() == report["default_checkpoint_sha256"]
print("Default checkpoint unchanged")'''),
        ("md", "## Error analysis / conclusion\n\nXem MAE/RMSE/bias từng chu vi và subgroup JSON để tránh chỉ nhìn trung bình. Không so chênh lệch với Phase 2 như cải thiện thuần kiến trúc: số người fit khác nhau. Dataset/test đã được xem ở phase trước, chưa có test mới prospective hoặc nhiều seed; không tự đổi default theo test. XGBoost/ViT chưa thử ở lượt này."),
    ])
    write("12_uncertainty_calibration.ipynb", "# 12 — Subject-level uncertainty calibration\n\n**Research question:** Khoảng dự đoán có đạt mức bao phủ danh nghĩa trên các test chưa tham gia calibration mới không?\n\nBaseline: absolute-residual split conformal, nominal 90%; max qua ảnh/người, thêm joint max qua ba target. Calibration tách khỏi toàn bộ fit/normalization/BN/epoch selection mới.", [
        ("code", '''import math
for name, result in report["results"].items():
    cal = result["calibrator"]
    assert cal["order_statistic_rank"] == math.ceil((cal["calibration_subjects"] + 1) * (1 - cal["alpha"]))
    assert cal["checkpoint_sha256"] == result["checkpoint_sha256"]
    print(name, "n=", cal["calibration_subjects"], "rank=", cal["order_statistic_rank"],
          "radii=", cal["per_target_radius_cm"], "joint radius=", cal["joint_radius_cm"])'''),
        ("code", '''from src.multimodal.calibration import interval_metrics
rows = ["| Variant | Test | Joint all-photo subject coverage | Joint full width (cm) |", "|---|---|---:|---:|"]
for name, result in report["results"].items():
    for test in ["testA", "testB"]:
        with np.load(ROOT / f"data/processed/bodym_phase3/{name}/{test}_predictions.npz") as data:
            actual = interval_metrics(data["y"], data["prediction"], data["subject_ids"], result["calibrator"])
        assert actual == result["tests"][test]["interval"]
        rows.append(f"| {name} | {test} | {actual['joint_subject_all_targets_all_photos_coverage']:.1%} | {actual['joint_width_cm']:.3f} |")
display(Markdown("\\n".join(rows)))'''),
        ("code", '''import matplotlib.pyplot as plt
name, test = "fusion", "testB"
with np.load(ROOT / f"data/processed/bodym_phase3/{name}/{test}_predictions.npz") as data:
    _, first = np.unique(data["subject_ids"], return_index=True)
    index = first[:12]  # Deterministic first 12 subjects, not selected by errors.
    pred, truth = data["prediction"][index, 0], data["y"][index, 0]
radius = report["results"][name]["calibrator"]["joint_radius_cm"]
fig, ax = plt.subplots(figsize=(10, 4))
ax.errorbar(np.arange(len(index)), pred, yerr=radius, fmt="o", capsize=3, label="Prediction + joint box radius")
ax.scatter(np.arange(len(index)), truth, marker="x", color="red", label="3D-mesh reference")
ax.set_xlabel("Deterministic subject index (one photo each)"); ax.set_ylabel("Chest (cm)")
ax.set_title("Interval examples only; coverage computed over full subject bundles")
ax.legend(); fig.tight_layout(); plt.show()'''),
        ("md", "## Error analysis / conclusion\n\nBáo độ bao phủ từng target, joint, width và subject-balanced pair coverage riêng. Một ảnh vượt khoảng khiến all-photo subject coverage thất bại. TestA có nhiều ảnh/người hơn calibration nên max-error distribution có thể đổi; testB cũng khác capture domain.\n\nKhông biến mức danh nghĩa 90% thành xác suất đúng cho một cá nhân, không khẳng định bảo đảm khi exchangeability/predictor independence không thỏa. Pipeline từng dùng dữ liệu này trước đây; cần đánh giá prospective mới. Không gắn calibrator vào default đã học mọi người train. Tham khảo [Angelopoulos & Bates](https://arxiv.org/abs/2107.07511)."),
    ])
    write("13_ood_and_model_card.ipynb", "# 13 — Novelty flags, inference & model card\n\n**Research question:** Có thể gắn cờ phạm vi dữ liệu và ràng buộc model/calibrator khi suy luận không?\n\nBaseline: median/IQR-distance trên metadata + geometry, threshold quantile 99% proper-fit, không dùng calibration/test. Đây là heuristic, chưa phải detector OOD có nhãn benchmark.", [
        ("code", '''detector = json.loads((ROOT / "models/bodym_phase3/novelty.json").read_text())
print("Novelty fit subjects:", detector["training_subjects"], "features:", len(detector["feature_names"]))
print("Threshold:", detector["threshold"], detector["limitations"])
display(report["ood"])'''),
        ("code", '''from scripts.run_bodym_baseline import read_csv
from src.multimodal.inference import estimate_pair
import torch
torch.set_num_threads(4)
with np.load(ROOT / "data/processed/bodym_phase3/fusion/testB_predictions.npz") as data:
    subject, photo = str(data["subject_ids"][0]), str(data["photo_ids"][0])
    expected = data["prediction"][0].copy()
metadata = {r["subject_id"]: r for r in read_csv(ROOT / "data/raw/bodym/testB/hwg_metadata.csv")}[subject]
quality = json.loads((ROOT / "configs/bodym_phase2.json").read_text())["quality"]
model_dir = ROOT / "models/bodym_phase3"
result = estimate_pair(model_dir / "fusion/model.pt", model_dir / "fusion/calibration.json", model_dir / "novelty.json",
    ROOT / "data/raw/bodym/testB/mask" / (photo + ".png"), ROOT / "data/raw/bodym/testB/mask_left" / (photo + ".png"),
    float(metadata["height_cm"]), float(metadata["weight_kg"]), metadata["gender"], quality)
from src.multimodal.model import load_ablation
from scripts.run_bodym_cnn import tensor_data, predictions
model, checkpoint = load_ablation(model_dir / "fusion/model.pt", "cpu")
with np.load(ROOT / "data/processed/bodym/cnn_128x96_testB.npz") as cached:
    sample = {key: cached[key][:1] for key in ["images", "metadata", "y", "subject_ids", "photo_ids"]}
assert str(sample["photo_ids"][0]) == photo
cpu_cached = predictions(model, tensor_data(sample, checkpoint["normalization"], torch.device("cpu")), checkpoint["normalization"], 1)[0]
actual = np.array([result["estimates"][key]["point_cm"] for key in ["chest", "waist", "hip"]])
np.testing.assert_allclose(actual, cpu_cached, atol=1e-6, rtol=0)
verification = {"sample": "first testB pair", "cpu_raw_cached_max_abs_difference_cm": float(np.abs(actual - cpu_cached).max()),
                "cpu_vs_recorded_batched_backend_max_abs_difference_cm": float(np.abs(actual - expected).max()),
                "note": "Same-backend raw/cache checked at 1e-6 cm. CPU vs recorded GPU/batch arithmetic reported separately; CUDA cuDNN TF32 was enabled in measured GPU run."}
(ROOT / "experiments/bodym_phase3/inference_verification.json").write_text(json.dumps(verification, indent=2) + "\\n", encoding="utf-8")
print(verification)
assert result["research_only"] and result["provenance"] == "inferred" and result["requires_review"]
display(result)'''),
        ("code", '''display(Markdown((ROOT / "models/bodym_phase3/MODEL_CARD.md").read_text(encoding="utf-8")))'''),
        ("md", "## Metrics / error analysis / conclusion\n\nJSON có flagged/unflagged errors/intervals, nhưng không có OOD ground truth nên không báo AUROC hoặc gọi unflagged là an toàn. Quality/novelty flags không được biến mất khi trả prediction; mọi số đo vẫn inferred/unverified. Nhãn gender do người cung cấp, không suy luận từ ảnh. Model card ghi dữ liệu, protocol, intended use và giới hạn.\n\nCòn thiếu: RGB/phone domain validation, nhiều seed, test mới, privacy/consent và safety screening production. Phase 4 tiếp theo là temporal alignment và progress/trend analysis có phân biệt observed/extracted/inferred."),
    ])


if __name__ == "__main__":
    create()
