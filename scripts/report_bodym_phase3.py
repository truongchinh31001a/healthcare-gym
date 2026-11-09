"""Render Phase 3 tables, research model card and standalone scientific plots."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

TARGETS = ("chest", "waist", "hip")


def write_artifacts(report, output, model_root):
    output, model_root = Path(output), Path(model_root)
    variants = list(report["results"])
    counts = report["subject_counts"]
    lines = ["# Phase 3 — Multimodal ablation & uncertainty", "",
             "Các checkpoint nghiên cứu mới; model mặc định Phase 2 giữ nguyên.", "",
             "## Protocol", "",
             f"Proper fit: {counts['proper_fit']}; tuning: {counts['tuning']}; calibration: {counts['calibration']} người.",
             f"Mỗi biến thể chọn epoch bằng tuning rồi refit trên {report['refit_subjects']} người proper-fit+tuning, loại calibration.",
             "Outer train/testA/testB giữ nguyên. testA/testB chung 1 subject ID, báo riêng.",
             "Tabular-only/image-only thực sự bỏ nhánh còn lại; không dùng zero-mask để giả lập ablation.",
             "Model default đã học cả 2.018 người nên không dùng calibrator mới cho checkpoint đó.",
             "", "## Point errors — subject-balanced, cm", "",
             "| Variant | Parameters | Best epoch | Tune MAE | Test | Chest MAE | Waist MAE | Hip MAE | Mean MAE |",
             "|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for name, result in report["results"].items():
        for split, scores in result["tests"].items():
            point = scores["point"]
            lines.append(f"| {name} | {result['parameters']} | {result['selection']['selected_epoch']} | {result['selection']['tuning_mean_mae_cm']:.3f} | {split} | " +
                         " | ".join(f"{point['mae_cm'][key]:.3f}" for key in TARGETS) + f" | {point['mean_mae_cm']:.3f} |")
    nominal = 1 - report["config"]["alpha"]
    lines += ["", f"## Intervals — nominal {nominal:.0%}", "",
              "Calibration score: max absolute error qua mọi ảnh của mỗi người. Dùng order statistic ceil((n+1)×(1−alpha)), không dùng quantile n thông thường.",
              "Per-target radii dành cho từng chu vi; joint radius là max qua cả ba chu vi để đánh giá đồng thời.",
              "Độ bao phủ dưới đây đòi hỏi mọi ảnh của người đó đều được bao phủ; pair coverage và width riêng có trong metrics JSON.", "",
              "| Variant | Test | Chest coverage | Waist coverage | Hip coverage | Joint coverage | Joint full width (cm) |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for name, result in report["results"].items():
        for split, scores in result["tests"].items():
            interval = scores["interval"]
            values = [interval["per_target_subject_all_photos_coverage"][key] for key in TARGETS]
            values += [interval["joint_subject_all_targets_all_photos_coverage"]]
            lines.append(f"| {name} | {split} | " + " | ".join(f"{v:.1%}" for v in values) + f" | {interval['joint_width_cm']:.3f} |")
    lines += ["", "Khoảng rộng không tự chứng minh hữu ích; đọc coverage cùng width. Target 90% là mức danh nghĩa, không phải xác suất đúng cho từng người.",
              "Số ảnh/người và điều kiện chụp giữa calibration/test khác nhau; đặc biệt testA có nhiều ảnh/người hơn. Không khẳng định bảo đảm coverage ngoài miền.",
              "", "## Novelty / OOD heuristic", "",
              "Median/IQR-distance trên 19 features (metadata + hình học silhouette), chỉ fit 1 ảnh/người ở proper-fit.",
              "Threshold là quantile 99% train; thêm cờ metadata ngoài min/max train. Không học từ calibration/test.",
              "Không có nhãn OOD thật nên chưa có AUROC/recall hoặc ngưỡng an toàn được kiểm chứng.", "",
              "| Test | Flagged pairs | All pairs | Subjects with any flag |", "|---|---:|---:|---:|"]
    for split, value in report["ood"].items():
        lines.append(f"| {split} | {value['flagged_pairs']} | {value['photo_pairs']} | {value['subjects_with_any_flag']} |")
    lines += ["", "Cờ không loại trường hợp khỏi overall metrics. Flagged/unflagged errors và intervals có trong metrics JSON; khi chỉ giữ một số ảnh thì coverage cũng chỉ áp dụng cho số ảnh đó.",
              "", "![Ablation and interval coverage](comparison.png)", "", "## Error analysis & conclusion", ""]
    if "fusion" in report["results"]:
        for split in ("testA", "testB"):
            fusion = report["results"]["fusion"]["tests"][split]
            lines.append(f"- {split}: fusion MAE {fusion['point']['mean_mae_cm']:.3f} cm, joint coverage {fusion['interval']['joint_subject_all_targets_all_photos_coverage']:.1%}.")
        lines.append("- Fusion chưa đạt coverage danh nghĩa 90% trên hai test này: uncertainty deployment gate chưa qua. Không chọn radius lại dựa trên test; cần validation/calibration đại diện hơn và test mới.")
    lines += ["- Khác biệt ba biến thể dùng cùng dữ liệu train/calibration là ablation nghiên cứu; một seed chưa chứng minh kết quả ổn định.",
              "- Không so trực tiếp delta với checkpoint default như một cải thiện model: default học 2.018 người, các model mới chỉ refit trên 1.695.",
              "- Data/architecture/test đã được xem ở các phase trước; không phải benchmark prospective hoàn toàn độc lập. Cần test mới trước phát hành.",
              "- Các giá trị là inferred từ silhouette, chưa được người dùng xác minh; không dự đoán thành phần mỡ/cơ, không dùng cho chẩn đoán.",
              "- Không tự chuyển model mặc định theo test. XGBoost/ViT, nhiều seed và dataset RGB ngoài miền chưa được đánh giá ở lượt này.",
              "", "Tham khảo phương pháp: [Angelopoulos & Bates — conformal prediction](https://arxiv.org/abs/2107.07511).", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    positions = np.arange(len(variants))
    for split, offset in (("testA", -.18), ("testB", .18)):
        bars = axes[0].bar(positions + offset, [report["results"][name]["tests"][split]["point"]["mean_mae_cm"] for name in variants], .35, label=split)
        axes[0].bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        coverage = [report["results"][name]["tests"][split]["interval"]["joint_subject_all_targets_all_photos_coverage"] for name in variants]
        bars = axes[1].bar(positions + offset, coverage, .35, label=split)
        axes[1].bar_label(bars, labels=[f"{value:.1%}" for value in coverage], padding=3, fontsize=9)
    axes[0].set_ylabel("Subject-balanced mean MAE (cm)")
    axes[0].set_title("Matched ablations: same 1,695 refit subjects")
    axes[1].axhline(nominal, color="black", linestyle="--", label=f"Nominal {nominal:.0%}")
    axes[1].set_ylabel("All-target, all-photo subject coverage")
    axes[1].set_ylim(0, 1)
    axes[1].set_title("Subject-max conformal; 323 calibration subjects")
    for ax in axes:
        ax.set_xticks(positions, [name.replace("_", " ") for name in variants])
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, .91))
    fig.savefig(output / "comparison.png", dpi=170)
    plt.close(fig)

    fusion = report["results"].get("fusion")
    card = ["# Model card — BodyM Phase 3 research fusion", "",
            "## Identity / intended use", "",
            "Research-only checkpoint `models/bodym_phase3/fusion/model.pt`; trained from scratch on BodyM silhouettes.",
            "Does not replace the selected default `models/bodym_cnn/model.pt`. For reproducible adult body-circumference research, non-commercial use pending license clarification.",
            "Inputs: ordered front/side binary silhouettes, provided height (cm), weight (kg), gender encoded by dataset male/female labels. Outputs: chest/waist/hip (cm).",
            "Does not infer gender, fat percentage, muscle mass, visceral fat or InBody values. Not validated for RGB phone photos, diagnosis, children, pregnancy or clinical planning.",
            "", "## Dataset / training", "",
            f"Seed {report['config']['seed']}; proper fit {counts['proper_fit']}, epoch tuning {counts['tuning']}, calibration {counts['calibration']}, final refit {report['refit_subjects']} subjects.",
            "Calibration subjects excluded from all new fitting, target/metadata normalization, BatchNorm and epoch selection. Split list/hashes/configs saved with experiment.",
            "Labels computed from registered 3D-scan meshes. Multiple photos per person; subject-balanced training/metrics. testA/testB share one subject, reported separately.",
            "Existing architecture/hyperparameters and test sets were explored earlier; the new protocol cannot undo historical adaptive reuse.",
            "", "## Calibration / uncertainty", "",
            "Fixed 90% nominal subject-max split conformal. Each calibration subject contributes one maximum residual per target across all their photos; joint score also maximizes across targets.",
            "Theoretical coverage needs exchangeability of subject bundles and an independently fixed predictor. Different photo counts, capture domains and historical selection limit that interpretation here.",
            "Empirical coverage/widths are research metrics, not per-person certainty or clinical tolerance. Calibration is cryptographically bound to its checkpoint; never attach it to the all-train default model.",
            "", "## Evaluation", ""]
    if fusion:
        card += [f"Checkpoint SHA256: `{fusion['checkpoint_sha256']}`.",
                 f"Parameters: {fusion['parameters']}; selected epoch: {fusion['selection']['selected_epoch']}.", ""]
        for split, value in fusion["tests"].items():
            card.append(f"- {split}: mean MAE {value['point']['mean_mae_cm']:.3f} cm; joint all-photo subject coverage {value['interval']['joint_subject_all_targets_all_photos_coverage']:.1%}; joint full width {value['interval']['joint_width_cm']:.3f} cm.")
    card += ["", "Full per-target MAE/RMSE/bias, subgroup errors, interval widths and novelty-flag strata: `experiments/bodym_phase3/metrics.json`.",
             "The fusion intervals did not reach the nominal 90% joint coverage on these tests. The uncertainty deployment gate is not met. No radius was retuned on test outcomes.",
             "", "## Limitations / deployment gate", "",
             "One seed, no independent RGB/OOD benchmark, no age/ethnicity/device subgroup labels, binary gender labels inherited from source, no validated acceptable-error threshold.",
             "Novelty score is a training-derived heuristic, not a safety classifier. Mask quality flags cannot certify anatomical completeness/pose. Do not suppress flags or treat predictions as observed measurements.",
             "Silhouette/image research needs protected storage and separate processing/research consent before collecting user data. No production authentication, retention or medical safety screening is supplied by this research pipeline.",
             "Requires new consented paired-data evaluation, uncertainty/domain validation and application review flow before user-facing release.",
             "", "Sources: [BodyM](https://registry.opendata.aws/bodym/), [measurement provenance](https://adversarialbodysim.github.io/), [conformal reference](https://arxiv.org/abs/2107.07511).", ""]
    (model_root / "MODEL_CARD.md").write_text("\n".join(card), encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    output = root / "experiments/bodym_phase3"
    report = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    write_artifacts(report, output, root / report["config"]["model_dir"])
