# Module 01 — triển khai từng bước

Theo `Module_01_User_and_Body_Profile.md`, ưu tiên hiện tại là **Phase 1 — InBody
Document AI**. Nhánh BodyM/CNN đã có kết quả; tích hợp backend/mobile nằm sau
nghiên cứu và evaluation gates. Thư mục `ai-personal-health-assistant` hiện giữ
vai trò khung ứng dụng.

## Bước 1 — Dữ liệu và schema

Đã thực hiện:

- Manifest nguồn với trạng thái quyền sử dụng và dữ liệu thực có; không coi dataset
  receipt/form là benchmark InBody. Chưa tải FUNSD/SROIE/phiếu mẫu của hãng.
- 16 phiếu giả lập từ layout tự thiết kế, seed 42; 8 dev + 8 smoke_test. Ảnh nằm
  trong `data/raw/inbody_synthetic`, nhãn trong `data/annotations/inbody_synthetic`.
- Hash ảnh/annotation, tách người/phiếu gốc, JSON Schema và guideline gán nhãn.
- 9 trường: weight, height, SMM, BFM, PBF, TBW, ECW/TBW, BMR và BMI.

Mở `notebooks/01_ocr_dataset_exploration.ipynb`. Schema xuất tại
`schemas/inbody_extraction.schema.json`, registry tại `configs/inbody_fields.json`.

## Bước 2 — Preprocessing và OCR baseline

Đã thực hiện:

- Ảnh/PDF local → EXIF transpose → grayscale/autocontrast, giữ nguyên nguồn.
- PaddleOCR 3.7.0, PaddlePaddle 3.3.1, PP-OCRv5 mobile detection + English recognition,
  CPU; chạy trong `.venv-ocr`, tách môi trường BodyM CUDA.
- Giữ tokens, bbox, confidence, kết quả ghép hàng và hash nguồn ở `data/processed`.
- Benchmark `paddle` thực chạy từ pixel; chế độ `oracle` tách riêng để kiểm parser
  bằng transcript và không báo CER/WER.

Mở `02_inbody_preprocessing.ipynb` và `03_ocr_baseline.ipynb` trong `notebooks`.
Báo cáo chạy thử ở `experiments/inbody_paddle_smoke/report.md`.
Đây là **smoke test synthetic**, không phải chất lượng InBody thật.

## Bước 3 — Parser, validation và review

- Chuẩn hóa kg/lb, cm/in và dấu thập phân dot/comma; giữ raw evidence.
- Thiếu đơn vị, thiếu trường, nhiều ứng viên, confidence thấp, outlier hoặc logic
  không nhất quán được gắn cờ; không đoán giá trị hoặc xóa outlier.
- Mỗi extraction có `pending_user_review`. Người xem chọn trường, sửa hoặc xác
  nhận cờ lỗi; tạo record xác nhận riêng cùng audit, không ghi đè draft.
- `confirmed_by_user` mô tả việc người dùng kiểm tra bản chép phiếu thiết bị;
  provenance vẫn `extracted`, không trở thành phép đo lâm sàng tham chiếu.
- Hàm review chỉ là nghiên cứu local, chưa phải API/auth/consent store production.

Mở `notebooks/04_inbody_information_extraction.ipynb` để xem demo sửa lỗi và audit.

## Cách chạy lại

Từ thư mục gốc `healthcare-ai-research` trên Windows PowerShell:

```powershell
# Chỉ cần khi tạo môi trường mới. Không cài vào .venv BodyM.
python -m venv .venv-ocr
.venv-ocr/Scripts/python.exe -m pip install -r requirements-ocr-lock.txt
.venv-ocr/Scripts/python.exe -m ipykernel install --user --name inbody-ocr --display-name "Python (InBody OCR)"

.venv-ocr/Scripts/python.exe scripts/prepare_inbody_synthetic.py
.venv-ocr/Scripts/python.exe scripts/run_inbody_ocr.py --engine oracle
.venv-ocr/Scripts/python.exe scripts/run_inbody_ocr.py --engine paddle
.venv-ocr/Scripts/python.exe -m unittest discover -s tests -p test_inbody_document_ai.py -v
.venv-ocr/Scripts/python.exe scripts/execute_inbody_notebooks.py
```

`requirements-ocr.txt` là các dependency trực tiếp; lock là snapshot đã chạy trên
Windows/Python 3.11. Model OCR tải từ nguồn chính thức khi chạy lần đầu, cache tại
`~/.paddlex/official_models`. Các ảnh được xử lý local; cần mạng cho tải model,
không cần gửi phiếu tới dịch vụ OCR ngoài. Lock chưa bao gồm checksum model weights.

Notebook `03` mặc định đọc kết quả đã chạy, đối chiếu config/hash manifest để tiết
kiệm thời gian; đặt `RERUN_INFERENCE=True` để đo lại. Bốn notebook mới dùng tên theo
roadmap; các notebook placeholder cũ được giữ nguyên. Không chạy lại script tạo
notebook lên file đang chỉnh sửa (script sẽ từ chối ghi đè).

Chạy ảnh/PDF riêng sau khi có quyền xử lý:

```powershell
.venv-ocr/Scripts/python.exe scripts/run_inbody_ocr.py --input "C:/private/report.pdf"
```

Kết quả ghi vào `data/processed/inbody_private/<hash>/`, gồm `ocr.json`,
`extraction.json`, `provenance.json` và các trang preprocessing. CLI không tự xác
nhận hay ghi dữ liệu vào ứng dụng. Dữ liệu thật cần lưu ở vùng bảo vệ, không Git.

## Bước 4 tiếp theo — Benchmark thật trước mở rộng

1. Thu thập phiếu ảnh/PDF được phép sử dụng, consent xử lý và consent nghiên cứu
   riêng; ẩn danh. Mẫu annotation tại `schemas/inbody_annotation.example.json`.
2. Hai người kiểm nhãn độc lập; khóa test theo subject/phiếu gốc, bổ sung holdout
   theo thiết bị/layout. Chưa có tài liệu thật trong workspace: **0 phiếu**.
3. Khảo sát layout để thêm crop/deskew, cột tham chiếu, tên thiết bị, ngày tháng,
   tiếng Việt, visceral/segmental fields. Chưa triển khai các trường này.
4. Đo baseline trên test thật, so OCR+rules với layout-aware/VLM khi đủ dữ liệu;
   correction rate phải đo từ phiên người dùng review thật.
5. Chốt ngưỡng chất lượng, model card và quy tắc fallback rồi mới tích hợp API,
   DB, bảo vệ file và màn hình review React Native/admin web.

## Đối chiếu 8 features

| Feature | Hiện trạng | Phần còn lại |
|---|---|---|
| F01 Personal Profile | Yêu cầu trong spec; app scaffold | Schema ứng dụng, API, mobile form, audit |
| F02 Body Measurements | BodyM có nhãn phục vụ nghiên cứu | Measurement sessions, unit conversion/audit trên app |
| F03 InBody Smart Scan | Pipeline local + schema + smoke benchmark + review demo | Real benchmark, layout-aware/VLM, protected storage, UI review |
| F04 Body Image Analysis | BodyM quality audit + preprocessing + CNN; subgroup/synthetic robustness report | RGB pose/segmentation, quality checks cho ảnh chụp, domain validation |
| F05 Composition Tracking | Phase 4 temporal/quality/trend pipeline + Dashboard/Planner JSON; synthetic study | Real longitudinal benchmark và app integration |
| F06 Weight Goals | Yêu cầu trong spec | Goal history và user approval |
| F07 Medical/Safety | Chưa triển khai | Consent store, unknown/negative, safety screening độc lập LLM |
| F08 Multimodal Intelligence | Phase 3 ablations, calibration/OOD heuristic và model card | Uncertainty gate chưa đạt; test mới, nhiều seed, RGB/domain validation |

Phase 1 **chưa hoàn tất** vì chưa có benchmark thật và các so sánh theo spec.
Synthetic đạt điểm cao cũng không đủ điều kiện phát hành tính năng cho người dùng.

## Chuyển sang Phase 2 theo yêu cầu

Tiếp tục nghiên cứu silhouette trên BodyM trong khi benchmark InBody thật chưa
có dữ liệu. Xem [Phase 2 — Body Image Intelligence](phase_02_body_image_intelligence.md)
cho dataset audit, quality/preprocessing, geometric features, subgroup và robustness.
Kết quả phase này không thay thế các evaluation gates còn thiếu của Phase 1.

## Phase 3 — Multimodal research

Xem [Phase 3](phase_03_multimodal_ml.md) cho matched ablations, calibration holdout,
interval coverage, novelty flags và model card. Default CNN refit toàn bộ train
được giữ nguyên; khoảng dự đoán thuộc các checkpoint nghiên cứu mới, không gắn
vào default đã học toàn bộ người train.

## Phase 4 — Body Progress Intelligence

Xem [Phase 4](phase_04_body_progress_intelligence.md): measured/recorded time,
as-of snapshots, audit/revisions, source-isolated trends và dữ liệu cho Dashboard/
Planner. Thử trên 193 bản ghi giả lập; chưa có benchmark longitudinal thật.
JSON/schema là đầu vào chuẩn bị tích hợp Phase 5, không tự tạo plan hoặc đổi goal.

## Nguồn đã đối chiếu

- [PaddleOCR API chính thức](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html).
- [FUNSD Terms of Use](https://guillaumejaume.github.io/FUNSD/work/).
- [DocLayNet dataset card](https://huggingface.co/datasets/docling-project/DocLayNet).


Phase 5 đã có [MVP tích hợp ứng dụng](phase_05_production_integration.md); xem phạm vi và gates còn lại trong báo cáo.


## Cập nhật OCR 22/10/2026

Đã tích hợp [PP-OCRv6 + spatial extraction](ocr_v6_spatial_extraction.md) và giữ baseline V5.
Config `configs/inbody_ocr.json` hiện là ứng viên V6; notebook 03 dùng config lịch sử riêng.
[So sánh 16 phiếu giả lập](../../experiments/inbody_ocr_comparison_v1/report.md) cho thấy V5 + layout
F1 0,902, V6 + layout 0,803. Chưa có benchmark InBody thật hoặc phê duyệt bật OCR trong app.
