"""Create the three Phase 4 notebooks without overwriting existing research."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
SETUP = '''from pathlib import Path
import sys, json
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "Module_01_User_and_Body_Profile.md").exists())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from IPython.display import display, Markdown
config = json.loads((ROOT / "configs/progress_phase4.json").read_text(encoding="utf-8"))
progress = json.loads((ROOT / "experiments/body_progress_phase4/progress.json").read_text(encoding="utf-8"))
'''


def write(name, question, cells):
    path = ROOT / "notebooks" / name
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    notebook = nbf.v4.new_notebook(cells=[nbf.v4.new_markdown_cell(question), nbf.v4.new_code_cell(SETUP)] + [
        nbf.v4.new_markdown_cell(text) if kind == "md" else nbf.v4.new_code_cell(text) for kind, text in cells])
    notebook.metadata.kernelspec = {"name": "bodym-research", "language": "python", "display_name": "Python (BodyM Research)"}
    nbf.write(notebook, path)
    print(path)


def create():
    write("14_temporal_alignment_and_quality.ipynb", "# 14 — Temporal alignment & quality\n\n**Research question:** Có thể căn chỉnh dữ liệu không đều theo ngày, giữ provenance và tái tạo snapshot tại một mốc chốt mà không dùng thông tin tương lai không?\n\nDataset: 193 bản ghi tự tạo, 5 subject giả lập, không có người thật. BodyM không phải dataset lịch sử số đo; không biến photo order thành ngày đo.", [
        ("code", '''import hashlib
from collections import Counter
from jsonschema import Draft202012Validator
manifest = json.loads((ROOT / "data/manifests/progress_synthetic_v1.json").read_text())
raw_path = ROOT / manifest["input"]
assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == manifest["sha256"]
rows = json.loads(raw_path.read_text())
schema = json.loads((ROOT / "schemas/body_progress_observation.schema.json").read_text())
for row in rows:
    Draft202012Validator(schema).validate(row)
print("Dataset:", manifest["dataset_id"], "records:", len(rows), "real subjects:", manifest["real_subjects"])
print("As of:", config["as_of"], "timezone:", config["report_timezone"])
print("States:", dict(Counter(row["analysis_state"] for row in progress["audit_rows"])))'''),
        ("md", "## Baseline / experiment config\n\nChuẩn hóa kg/lb, cm/in theo registry; giữ giá trị/đơn vị gốc. Timestamp phải có UTC offset; date-only không được gán giờ đo giả, chỉ căn theo lịch khi timezone rõ. Dùng ngày đo cho chuỗi; dùng recorded_at để lọc kiến thức có tại mốc chốt. Không dùng upload time thay capture time. Model mặc định giữ nguyên."),
        ("code", '''sample = next(row for row in progress["audit_rows"] if row["unit"] == "lb")
display({key: sample[key] for key in ["observation_id", "value", "unit", "canonical_value", "canonical_unit", "day", "provenance"]})
display([{key: row.get(key) for key in ["observation_id", "value", "recorded_at", "analysis_state", "quality_flags"]}
         for row in progress["audit_rows"] if row["analysis_state"] in ["superseded", "not_yet_recorded", "quarantined_conflicting_id"]])'''),
        ("code", '''from src.body_progress.engine import build_progress
rebuilt = build_progress(rows, config)
assert rebuilt == progress
assert len(progress["audit_rows"]) == len(rows)
print("Rebuild identical, all raw input records retained in local audit")'''),
        ("md", "## Metrics / error analysis / conclusion\n\nID trùng cùng nội dung chỉ tính một lần; cùng ID khác nội dung bị cách ly. Sửa đổi cần parent cùng sự kiện/nguồn, recorded_at muộn hơn và audit reason/actor; nhánh xung đột cần review, không tự chọn bản mới nhất. Bản ghi đến sau mốc chốt vẫn ở audit nhưng không ảnh hưởng stream, flags hoặc context của snapshot quá khứ.\n\nUnit tests có case bản ghi trùng ID đến muộn, timezone, NaN, missing và inferred cố nhận trạng thái verified. Những kiểm tra này kiểm phần mềm, không xác thực dữ liệu sức khỏe thực tế."),
    ])
    write("15_body_progress_analysis.ipynb", "# 15 — Body progress & change analysis\n\n**Research question:** Có thể khôi phục xu hướng định trước, giữ nguồn riêng và ngừng tính trend khi thiếu dữ liệu/quality chưa đủ không?\n\nDataset synthetic v1, seed 42 (generator xác định). Baseline: daily median → calendar/rolling-week medians → Theil-Sen slope theo ngày thực tế, chỉ trên reviewed observations.", [
        ("code", '''metrics = json.loads((ROOT / "experiments/body_progress_phase4/metrics.json").read_text())
print("Expected slope (fixture only):", metrics["expected_primary_slope_kg_per_week"])
print("Recovered:", metrics["recovered_primary_slope_kg_per_week"], "absolute error:", metrics["trend_recovery_abs_error"])
assert metrics["trend_recovery_abs_error"] < 1e-8
rows = ["| Subject | Field | Provenance | Device | Days with values | Slope/week | Reasons withheld |", "|---|---|---|---|---:|---:|---|"]
for stream in progress["series"]:
    trend = stream["trend"]
    slope = f"{trend['slope_per_week']:.3f}" if trend["slope_per_week"] is not None else "N/A"
    rows.append(f"| {stream['subject_id']} | {stream['field']} | {stream['provenance']} | {stream['device_id']} | {stream['days_with_values']} | {slope} | {', '.join(trend['withheld_reasons'])} |")
display(Markdown("\\n".join(rows)))'''),
        ("code", '''from PIL import Image
display(Image.open(ROOT / "experiments/body_progress_phase4/progress.png"))
review = next(s for s in progress["series"] if s["subject_id"] == "synthetic-review")
assert review["trend"]["slope_per_week"] is None
print("Outlier maximum retained:", max(day["value"] for day in review["days"] if day["value"] is not None))
sparse = next(s for s in progress["series"] if s["subject_id"] == "synthetic-sparse")
display(sparse["gaps"])
assert len(sparse["days"]) == 3  # No forward-fill/interpolation.'''),
        ("code", '''pbf = next(s for s in progress["series"] if s["subject_id"] == "synthetic-steady" and s["field"] == "percent_body_fat" and s["provenance"] == "observed")
assert pbf["recent_week_comparison"]["change_unit"] == "percentage_points"
primary = next(s for s in progress["series"] if s["subject_id"] == "synthetic-steady" and s["field"] == "weight_kg" and s["device_id"] == "scale-A")
display(primary["recent_week_comparison"])
print("Statistical confidence:", primary["trend"]["statistical_confidence"])'''),
        ("md", "## Error analysis / conclusion\n\nHệ số -0,28 kg/tuần chỉ là nhãn fixture, không phải mục tiêu/khuyến nghị giảm cân. Không gộp sensor A/B, observed/confirmed-OCR/inferred, protocol hoặc model version. Nhiều lần đo trong ngày không lấn át tuần. PBF đổi theo điểm phần trăm; reference 0 không chia cho 0 và không coi là missing.\n\nCác ngưỡng đổi nhanh, gap/stale, số ngày là engineering heuristics. Trend bị giữ lại nếu cờ chưa xử lý hoặc dữ liệu quá thưa/cũ; không xóa outlier hay đoán ngày còn thiếu. Chưa có longitudinal benchmark thực, device repeatability hoặc calibrated trend confidence. Theil-Sen chỉ mô tả dữ liệu; không forecast/causal/clinical conclusion. [Phương pháp SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html)."),
    ])
    write("16_progress_dashboard_and_planner_context.ipynb", "# 16 — Dashboard metrics & Planner context\n\n**Research question:** Có thể xuất facts có nguồn rõ ràng và chỉ đúng subject mà không tự tạo kế hoạch từ dữ liệu chưa xác minh không?\n\nBaseline: deterministic context builder + versioned JSON Schemas. Dùng cùng fixture synthetic, không gọi LLM, không sửa mục tiêu.", [
        ("code", '''from jsonschema import Draft202012Validator, FormatChecker
dashboard = json.loads((ROOT / "experiments/body_progress_phase4/dashboard.json").read_text())
context = json.loads((ROOT / "experiments/body_progress_phase4/planner_context.json").read_text())
selected_context = json.loads((ROOT / "experiments/body_progress_phase4/planner_context_selected_demo.json").read_text())
for name, payload in [("body_progress_dashboard", dashboard), ("body_progress_planner_context", context), ("body_progress_planner_context", selected_context)]:
    schema = json.loads((ROOT / "schemas" / (name + ".schema.json")).read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
assert "audit_rows" not in dashboard
assert all(s["subject_id"] == dashboard["subject_id"] for s in dashboard["series"])
print("Subject-scoped schemas passed")'''),
        ("code", '''print("Unselected source conflicts:")
display(context["needs_source_selection"])
print("Fixture's explicit source selection (not an automatic preference rule):")
display([{key: fact[key] for key in ["field", "provenance", "source", "measurement_method", "device_id", "verification_band"]} for fact in selected_context["facts"]])
assert all(fact["provenance"] in ["observed", "extracted"] and fact["verification_band"] == "reviewed" for fact in selected_context["facts"])
assert not selected_context["plan_generation_authorized"]
assert selected_context["requires_safety_screening"] and selected_context["goal_changes_require_user_approval"]
display(selected_context["interpretation_limits"])'''),
        ("md", "## Integration boundary / error analysis / conclusion\n\nAdapter Phase 1 giữ `extracted` sau human review, không đổi thành observed; không có ngày đo thì giữ null. Adapter Phase 3 cần capture timestamp do caller cung cấp, giữ `inferred`, checkpoint version, interval evidence và quality/OOD flags. Uncertainty deployment gate Phase 3 chưa qua nên không dùng ML vào planner facts.\n\nCó JSON/schema và CLI research, chưa có API/database/UI chạy trên người dùng. Consent ID chỉ là tham chiếu; server Phase 5 phải xác thực người dùng, quyền dữ liệu, consent store và safety screening độc lập LLM. Không có mục tiêu hay kế hoạch tự động thay đổi. Phase 4 hoàn thành thử phần mềm bằng synthetic; cần nguồn lịch sử đo có quyền sử dụng để kiểm thực tế."),
    ])


if __name__ == "__main__":
    create()
