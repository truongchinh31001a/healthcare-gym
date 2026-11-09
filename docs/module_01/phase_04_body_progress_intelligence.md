# Phase 4 — Body Progress Intelligence

Triển khai Pipeline C của Module 01: căn chỉnh phép đo theo thời gian, kiểm chất
lượng, tính chỉ số mô tả và xuất dữ liệu cho Dashboard/AI Planner. Phạm vi hiện
tại là **research pipeline local với fixture synthetic**, chưa phải app production.

## 1. Dữ liệu và phạm vi kiểm chứng

BodyM có nhiều ảnh/người nhưng không có lịch sử phiên đo theo ngày đã được xác
minh. Không suy ra ngày từ thứ tự ảnh. Chưa có nguồn lịch sử InBody/cân nặng thật
được đồng ý trong workspace; không dùng synthetic để tuyên bố accuracy y khoa.

Bộ thử riêng `body-progress-synthetic-v1`: 193 bản ghi, 5 subject giả, 12 streams,
không có người thật. Layout dữ liệu tự tạo; không sao chép phiếu/device record.
Các trường hợp gồm đổi kg/lb, date-only, hai cân có offset, observed/OCR/ML, sửa
lỗi, bản sao, xung đột ID, dữ liệu đến muộn/tương lai, outlier, gap, thưa và cũ.

Manifest có SHA256 input/expected labels, generator version và seed. Oracle slope
của một stream cân được đặt -0,28 kg/tuần; pipeline khôi phục đúng trong tolerance
1e-8. Đây chỉ là phép kiểm phần mềm, **không phải tốc độ giảm cân được khuyến nghị**.

## 2. Observation contract và provenance

Schema: `schemas/body_progress_observation.schema.json`.

Mỗi record có ID/subject/session/field, value/unit, measured_at/recorded_at,
measurement timezone, method/source, provenance/verification, device/model,
protocol, model version, consent reference, quality flags và synthetic marker.
Revisions bổ sung supersedes ID và audit actor/reason.

| Provenance/status | Dashboard | Reviewed trend / Planner facts |
|---|---|---|
| observed + verified/confirmed_by_user | Riêng stream | Có nếu đủ dữ liệu và vượt quality gates |
| extracted + confirmed_by_user | Giữ nhãn OCR, không đổi observed | Có nếu đủ dữ liệu/quality; không gộp với observed |
| extracted + pending_user_review | Riêng stream chờ review | Không |
| inferred + unverified_estimate | Riêng stream ước lượng | Không |
| declared | Riêng stream tự khai báo | Không coi là reviewed measurement |

Reviewed chỉ mô tả việc kiểm tra entry/transcription, không chứng minh ground
truth lâm sàng. BIA vẫn là ước lượng thiết bị, không tương đương DXA.

Adapter Phase 1 (`src/body_progress/adapters.py`) giữ extracted và ngày null khi
chưa biết. Adapter Phase 3 cần capture timestamp được cung cấp riêng, không lấy
inference/upload time làm ngày đo; giữ model version, interval evidence và cờ
uncertainty gate chưa qua. Không thay thế thực đo bằng ML.

## 3. Căn chỉnh thời gian và audit

- Timestamp cần UTC offset, được chuẩn hóa UTC; daily bins theo `Asia/Bangkok`
  hoặc timezone được truyền rõ khi chạy. Date-only giữ nguyên độ chính xác ngày;
  nếu thiếu/khác timezone không đủ thông tin đổi lịch thì yêu cầu review.
- `measured_at` xác định ngày đo; `recorded_at <= as_of` xác định record đã được
  biết tại mốc chốt. Không gán thời điểm đo từ ngày upload.
- Bản ghi đến muộn/tương lai giữ trong private audit. ID conflict hoặc model mới
  được ghi sau cutoff không được tác động tới stream/context quá khứ.
- Trùng ID/nội dung chỉ tính một lần; trùng ID khác nội dung cách ly. Cùng phiên,
  cùng field/stream mà giá trị khác nhau được gắn cờ; không tự chọn mới nhất.
- Sửa đổi cần cùng subject/session/field/source/method/device/model, recorded_at
  tăng và audit actor/reason. Chỉ revision reviewed có giá trị hợp lệ mới thay
  bản trước trong view phân tích; bản gốc vẫn ở audit. Nhánh sửa xung đột cần review.
- `active` là trạng thái revision, còn `temporal_eligible` quyết định có thể đưa
  vào timeline. `not_yet_recorded` không được xuất như nguồn đã có tại cutoff.

Các hàm là pure transformations và không ghi đè input, measurement hay goal.
Audit riêng giữ tất cả input hợp lệ; record sai schema được lưu ở danh sách invalid.
JSON NaN/Infinity bị từ chối. Consent ID chỉ là reference, không phải consent store.

## 4. Trend/change metrics và quality gates

Chuẩn đơn vị: kg, cm, L, %, ratio, kcal/day, kg/m2. Giữ raw value/unit cùng
canonical value; không đổi phần trăm thành tỉ số nếu chưa có quy tắc rõ.

Mỗi stream tách theo **subject + field + provenance + review band + source +
method + device + protocol + model version**. Không tự harmonize sensor A/B.

1. Median theo ngày, rồi median các ngày trong tuần lịch: đo nhiều lần cùng ngày
   không tạo trọng số lớn hơn cho ngày đó. Không nội suy/forward fill.
2. So median 7 ngày lịch hiện tại và 7 ngày trước đó, chỉ khi mỗi window có ít
   nhất 3 ngày có giá trị, là reviewed source và không có cờ cần xem lại.
3. Theil-Sen slope trên daily medians theo **ngày thực tế đã trôi qua**, window
   28 ngày; ít nhất 4 ngày có giá trị và span ít nhất 14 ngày. Chỉ trả mô tả,
   không forecast, causal claim, confidence probability hay đề xuất mục tiêu.
4. Cờ plausibility, thay đổi nhanh, thiết bị chưa rõ, session/revision conflict,
   gap lớn hoặc dữ liệu cũ làm giữ lại trend theo cấu hình. Không tự xóa outlier;
   dữ liệu/cờ vẫn hiển thị. Cờ derived như rapid change nằm ở daily view cùng IDs.
5. Khoảng trống thể hiện không có record, không được diễn giải là người dùng
   không tuân thủ. Không mặc định mọi field phải đo hàng ngày.
6. PBF change có đơn vị **percentage_points**; relative percent riêng. Reference
   bằng 0 thì relative change là null, không coi số 0 là missing.

Các ngưỡng trong `configs/progress_phase4.json` là engineering review heuristics,
chưa phải ngưỡng sinh học/lâm sàng hoặc kiểm chứng độ lặp lại của thiết bị.
`statistical_confidence=null`; chất lượng support/source không phải xác suất cải thiện.

Phương pháp: [SciPy Theil-Sen](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html).

## 5. Dữ liệu cho ứng dụng

- `dashboard_payload`: chỉ đúng subject, source-tagged series và quality summary;
  không gửi full raw audit hoặc dữ liệu người khác. Giá trị thiếu giữ null/gap.
- `planner_context`: chỉ facts từ reviewed streams có descriptive trend đủ support.
  Khi nhiều stream đủ điều kiện cùng field, trả `needs_source_selection`; không
  tự chọn nguồn dựa vào số mới nhất hoặc ưu tiên observed hơn confirmed OCR.
- Selection demo trong fixture dùng IDs được chọn rõ để minh họa; không phải
  chính sách tự động áp cho dữ liệu người dùng thật.
- Inferred/pending/self-declared/withheld streams không vào facts. Giữ method,
  device, protocol và provenance để Planner không hiểu sai ý nghĩa phép đo.
- `plan_generation_authorized=false`, `requires_safety_screening=true`,
  `goal_changes_require_user_approval=true`. Không gọi LLM hay tự đổi goal/plan.

Schemas: `schemas/body_progress_dashboard.schema.json`,
`schemas/body_progress_planner_context.schema.json`. Đây là contract nghiên cứu,
chưa có route API/DB/UI mới; Phase 5 phải bổ sung auth/authorization, consent store,
retention và safety screening độc lập LLM.

## Chạy và xem kết quả

Môi trường `.venv` hiện tại đã có dependency. Khi thiết lập mới, dùng
`requirements-progress.txt` (bao gồm core requirements, jsonschema và tzdata).

```powershell
.venv/Scripts/python.exe scripts/prepare_progress_synthetic.py
.venv/Scripts/python.exe scripts/run_body_progress.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_body_progress.py -v
.venv/Scripts/python.exe scripts/execute_progress_notebooks.py
```

Notebooks:

1. `14_temporal_alignment_and_quality.ipynb`: schema, units, as-of và audit.
2. `15_body_progress_analysis.ipynb`: known-trend check, gaps, outliers, biểu đồ.
3. `16_progress_dashboard_and_planner_context.ipynb`: subject scope, contracts và nguồn.

Artifacts tại `experiments/body_progress_phase4/`: report, metrics, progress.json,
dashboard.json, planner_context.json, selected-source demo và progress.png.
Input trong `data/raw/progress_synthetic/` (ignored), nhãn kỳ vọng và manifest được version.

Với dữ liệu riêng có quyền sử dụng, chuẩn bị JSON array theo observation schema:

```powershell
.venv/Scripts/python.exe scripts/run_body_progress.py --input C:/private/observations.json --as-of 2026-10-22T00:00:00+07:00 --timezone Asia/Bangkok --subject-id subject-id
```

Output chỉ vào `data/processed/progress_private/<hash>/` (ignored), không xuất
báo cáo công khai. Full progress/audit có thể bao gồm toàn bộ input file cho
nghiên cứu local; chỉ dashboard/planner là subject-scoped. Không expose audit
này như endpoint cho người dùng. Cần lưu dữ liệu riêng trong vùng có bảo vệ.

## Kết quả và giới hạn

Lượt thử: 193 records, 12 streams, 6 stream không xuất slope; khôi phục đúng slope
fixture, giữ outlier và original revision, tách pending/inferred. 18 unit tests
bao phủ time/unit/provenance/revision/snapshot/subject isolation và adapters.

Chưa có real longitudinal benchmark, noise/repeatability assessment hoặc clinical
validation. Phase 1 còn thiếu benchmark phiếu thật; Phase 3 uncertainty gate chưa
qua. Phase 4 không thay đổi default model hoặc biến dự đoán ML thành thực đo.

Tiếp theo: **Phase 5 — Production Integration**, triển khai dữ liệu/API/quyền truy
cập và review UI trong FastAPI, React Native, admin web; chỉ bật OCR/CV inference
cho người dùng khi evaluation/consent/safety gates tương ứng được đáp ứng.
