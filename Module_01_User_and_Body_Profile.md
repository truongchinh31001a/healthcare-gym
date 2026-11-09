# Module 01 — User & Body Profile

> **Project:** AI-Powered Personalized Weight Management  
> **Version:** 1.0 · 21/10/2026  
> **Scope:** Adult wellness — hỗ trợ giảm cân, tăng cân và duy trì cân nặng; ưu tiên nghiên cứu giảm mỡ/giảm cân. Không phải hệ thống chẩn đoán hay điều trị y khoa.  
> **Development strategy:** Dataset → Jupyter Notebook research → model evaluation → backend/application integration.

## 1. Mục tiêu

Module **User & Body Profile** tập trung lưu trữ, chuẩn hóa và phân tích dữ liệu hình thể của người dùng. Đây là nguồn dữ liệu đầu vào cho Health Dashboard, AI Weight Planner, AI Health Assistant và Weekly AI Review.

Các mục tiêu chính:

1. Quản lý hồ sơ, mục tiêu và các số đo cơ thể theo thời gian.
2. Số hóa phiếu kết quả InBody từ ảnh/PDF bằng OCR và Document AI.
3. Phân tích ảnh cơ thể (chính diện, bên hông; mặt sau tùy chọn) bằng Computer Vision.
4. Nghiên cứu ước lượng chu vi cơ thể bằng regression và multimodal learning.
5. Phân tích xu hướng cân nặng, số đo và thành phần cơ thể với nguồn gốc dữ liệu minh bạch.
6. Bảo đảm quyền riêng tư, sự đồng ý của người dùng và các ràng buộc an toàn.

**Nguyên tắc:** Mọi giá trị do OCR hoặc ML tạo ra đều là dữ liệu chưa xác nhận hoặc ước lượng; không tự động ghi đè giá trị thực đo đã được xác minh.

## 2. Phạm vi tính năng

| ID | Feature | Chức năng chính | Đầu ra |
|---|---|---|---|
| F01 | Personal Profile | Hồ sơ nền tảng, chiều cao, độ tuổi, đơn vị đo và lịch sử chỉnh sửa | `user_profiles` |
| F02 | Body Measurements | Nhập cân nặng, chiều cao và **chu vi** eo/hông/ngực/bắp tay/đùi; lưu phiên đo, đơn vị và nguồn | `body_measurement_sessions`, `anthropometric_measurements` |
| F03 | InBody Smart Scan | Ảnh/PDF → tiền xử lý → OCR → trích xuất trường → validation → người dùng xác nhận | `inbody_documents`, `inbody_extraction_jobs`, `body_composition_measurements` |
| F04 | AI Body Image Analysis | Hướng dẫn chụp, kiểm tra ảnh, pose, segmentation, silhouette và geometric features | `body_images`, `image_analysis_jobs` |
| F05 | Body Composition Tracking | Theo dõi cân nặng, SMM, BFM, PBF và xu hướng qua các phiên đo | Body trends, dashboard-ready metrics |
| F06 | Weight Goals | Mục tiêu giảm/tăng/duy trì, lịch sử thay đổi và xác nhận của người dùng | `health_goals`, `goal_history` |
| F07 | Medical & Safety Context | Giới hạn vận động, dị ứng, yếu tố sức khỏe liên quan và kiểm tra an toàn theo quy tắc | `medical_context_records`, `safety_assessments` |
| F08 | Multimodal ML Intelligence | Kết hợp ảnh + dữ liệu nhân trắc để ước lượng số đo; uncertainty và ablation | `ml_predictions`, `model_versions`, evaluation reports |

### F01 — Personal Profile

- Thu thập thông tin tối thiểu cần thiết cho việc cá nhân hóa; tránh thu thập dữ liệu nhạy cảm không cần thiết.
- Hỗ trợ đơn vị kg/lb và cm/in; chuẩn hóa đơn vị trong hệ thống.
- Tách dữ liệu đăng nhập/định danh khỏi dữ liệu sức khỏe.
- Lưu nguồn, thời điểm cập nhật và lịch sử chỉnh sửa.

### F02 — Body Measurements

- Nhập thủ công hoặc nhận dữ liệu từ nguồn được phép: chiều cao, cân nặng, chu vi eo/hông/ngực/bắp tay/đùi.
- Mỗi số đo có `measured_at`, `recorded_at`, `unit`, `measurement_method`, `source`, `verification_status`.
- Kiểm tra đơn vị, missing values, outliers và những thay đổi bất thường; không tự ý xóa số đo bất thường.
- Cho phép sửa số đo với audit trail.

### F03 — InBody Smart Scan

- Nhận ảnh chụp hoặc PDF phiếu InBody; xử lý crop, deskew, denoise và cải thiện độ rõ.
- OCR và nhận diện bố cục để trích xuất các trường tùy theo mẫu phiếu: Weight, Skeletal Muscle Mass (SMM), Body Fat Mass (BFM), Percent Body Fat (PBF), Total Body Water (TBW), ECW/TBW, BMR, BMI, các chỉ số visceral fat/segmental nếu có.
- Chuẩn hóa tên trường, đơn vị, dấu thập phân, ngày đo và thiết bị.
- Validation bằng kiểm tra miền giá trị, đơn vị, logic giữa các trường và confidence; không thay thế đánh giá chuyên môn.
- **Người dùng phải xem lại và xác nhận** trước khi ghi thành observation đã xác minh.
- Lưu tài liệu nguồn, model/parser version, kết quả OCR và lịch sử sửa.

### F04 — AI Body Image Analysis

- Hướng dẫn chụp ảnh chính diện và bên hông theo điều kiện nhất quán; ảnh mặt sau là tùy chọn.
- Kiểm tra chất lượng: tư thế, độ sáng, khoảng cách, ảnh thiếu phần cơ thể hoặc che khuất.
- Pose estimation, segmentation, silhouette extraction, geometric feature engineering.
- Nghiên cứu mô hình ước lượng chu vi từ ảnh khi có **nhãn số đo thực tế ghép cặp**.
- Không khẳng định có thể đo chính xác mỡ nội tạng, khối lượng cơ hoặc chu vi cm chỉ từ ảnh chưa hiệu chuẩn.

### F05 — Body Composition Tracking

- Biểu đồ cân nặng, chu vi và chỉ số InBody theo thời gian.
- So sánh giữa các phiên đo, nhận diện biến động và khoảng dữ liệu thiếu.
- Phân biệt số đo bằng thước, chỉ số thiết bị BIA/InBody và giá trị ML dự đoán.
- Hiển thị cảnh báo chất lượng dữ liệu, không biến thay đổi nhỏ thành kết luận sức khỏe chắc chắn.

### F06 — Weight Goals

- Hỗ trợ mục tiêu giảm cân, tăng cân hoặc duy trì; giai đoạn đầu ưu tiên giảm cân/giảm mỡ.
- Lưu chỉ số đích, thời gian dự kiến, sở thích, hạn chế và lịch sử mục tiêu.
- Mọi điều chỉnh mục tiêu hoặc kế hoạch do AI đề xuất phải được người dùng chấp thuận.

### F07 — Medical & Safety Context

- Thu thập có chọn lọc những thông tin liên quan: hạn chế vận động, dị ứng, tình trạng cần lưu ý, thuốc khi thực sự cần, thai kỳ/hậu sản, dấu hiệu rối loạn ăn uống hoặc các red flags phù hợp.
- Phân biệt `unknown` với `negative`; không suy đoán người dùng không có vấn đề sức khỏe chỉ vì chưa khai báo.
- Áp dụng **rule-based safety screening độc lập với LLM** khi tạo mục tiêu và trước khi đưa kế hoạch.
- Dừng hoặc chuyển hướng sang hỗ trợ chuyên môn khi phát hiện tình huống vượt phạm vi wellness.

### F08 — Multimodal ML Intelligence

- Thử nghiệm image encoder (CNN/ViT), tabular encoder và feature fusion.
- Dự đoán chu vi cơ thể với MAE/RMSE (cm), khoảng bất định và phân tích lỗi.
- So sánh tabular-only, geometric features + XGBoost, image-only và multimodal fusion.
- Tránh **target leakage**: không dùng chu vi eo đã biết để đánh giá mô hình dự đoán chính chu vi eo.
- Split theo **người tham gia**, không theo ảnh; đánh giá khả năng tổng quát hóa sang người chưa từng thấy.
- Nghiên cứu body composition prediction chỉ khi có dữ liệu ghép cặp và nhãn tham chiếu phù hợp. Chỉ số InBody/BIA là ước lượng của thiết bị, không tương đương ground truth DXA.

## 3. Các pipeline nghiên cứu

### Pipeline A — InBody Document AI

```text
InBody Image / PDF
        ↓
Image/PDF Preprocessing
        ↓
OCR + Layout Understanding
        ↓
Key Information Extraction
        ↓
Field Normalization + Validation
        ↓
Human Review / Confirmation
        ↓
Structured JSON + Verified Observation
```

**Các phương án so sánh:**

- E01: PaddleOCR + rule-based parser.
- E02: OCR + layout-aware extraction.
- E03: Vision Language Model (VLM).
- E04: Hybrid OCR + VLM + deterministic validation.

**Metrics:** CER/WER cho OCR khi có transcript; field-level exact match/F1; numeric MAE **riêng theo trường và đơn vị**; document success rate; correction rate; latency. Cần tập phiếu thật được gán nhãn thủ công và tập kiểm thử độc lập.

### Pipeline B — Body Image Intelligence

```text
Front / Side Body Images
        ↓
Image Quality Assessment
        ↓
Pose Estimation + Segmentation
        ↓
Silhouette / Geometric Features
        ↓
Image Encoder + Tabular Encoder
        ↓
Regression + Uncertainty Calibration
        ↓
Predicted Circumference + Confidence/Interval
```

**Các phương án so sánh:**

- B01: Tabular-only baseline.
- B02: Geometric features + XGBoost.
- B03: Image-only CNN/ViT.
- B04: Image + tabular fusion.
- B05: Fusion + uncertainty calibration.

**Metrics:** MAE/RMSE theo từng chu vi (cm), interval coverage, robustness theo tư thế/ánh sáng/thiết bị, subgroup analysis, latency. Kiểm tra train/validation/test split theo `subject_id`.

### Pipeline C — Body Progress Intelligence

```text
Verified Measurements + InBody History
        ↓
Temporal Alignment + Quality Checks
        ↓
Trend & Change Analysis
        ↓
Uncertainty / Data Source Explanation
        ↓
Dashboard Insights → AI Weight Planner
```

Không trộn giá trị ML dự đoán vào chuỗi dữ liệu thực đo mà không gắn nhãn nguồn.

## 4. Dataset strategy

| Nguồn | Vai trò | Lưu ý |
|---|---|---|
| FUNSD | Form understanding, token/box/field relations | Không chuyên biệt InBody |
| SROIE | OCR trên ảnh chứng từ, bounding boxes, key-value | Không chuyên biệt InBody |
| CORD | Receipt parsing và structured extraction | Không chuyên biệt InBody |
| DocLayNet | Document layout detection | Không phải OCR transcript dataset chính |
| InBody sample sheets | Khám phá layout và thử parser | Cần kiểm tra giấy phép, không mặc định được train/phân phối |
| InBody annotated real documents | Benchmark chuyên biệt | Thu thập có đồng ý, ẩn danh, chia train/test theo phiếu gốc/người/nguồn phù hợp |
| Synthetic InBody-like documents | Data augmentation, kiểm thử parser | Dùng template tự thiết kế hoặc được cấp quyền; không thay thế real-world test |
| BodyM | Silhouette + anthropometric labels cho regression | Kiểm tra điều kiện CC BY-NC và tính phù hợp trước dùng thương mại |
| Paired RGB + tape measurements + InBody | Nghiên cứu multimodal nâng cao | Khó thu thập; yêu cầu consent và nhãn đáng tin cậy |

**Tài nguyên tham khảo:**

- FUNSD: https://huggingface.co/datasets/davidle7/funsd-json
- SROIE: https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE
- CORD: https://huggingface.co/datasets/wkrl/cord
- DocLayNet: https://huggingface.co/datasets/docling-project/DocLayNet
- BodyM: https://registry.opendata.aws/bodym/
- InBody 380 sample catalog: https://www.inbodyvietnam.com/files/Inbody_380_catalog.pdf
- InBody download center: https://downloads.inbody.com/
- InBody OCR reference repository: https://github.com/DoctorDNA/InBody

> **Data availability:** Chưa xác minh được một bộ dữ liệu công khai lớn gồm ảnh/PDF phiếu InBody kèm nhãn JSON chuẩn. Bộ benchmark InBody-specific cần tự thiết kế và thu thập hợp pháp.

## 5. Notebook research roadmap

```text
healthcare-ai-research/
├── notebooks/
│   ├── 01_ocr_dataset_exploration.ipynb
│   ├── 02_inbody_preprocessing.ipynb
│   ├── 03_ocr_baseline.ipynb
│   ├── 04_inbody_information_extraction.ipynb
│   ├── 05_document_ai_benchmark.ipynb
│   ├── 06_bodym_dataset_exploration.ipynb
│   ├── 07_body_image_preprocessing.ipynb
│   ├── 08_body_measurement_baseline.ipynb
│   ├── 09_multimodal_fusion.ipynb
│   └── 10_model_evaluation.ipynb
├── data/
│   ├── raw/
│   ├── processed/
│   ├── annotations/
│   └── manifests/
├── src/
│   ├── document_ai/
│   ├── body_vision/
│   ├── multimodal/
│   └── validation/
├── models/
├── experiments/
├── configs/
├── reports/
├── requirements.txt
└── README.md
```

Mỗi notebook cần: **research question → dataset → baseline → experiment config → metrics → error analysis → conclusion**. Dùng fixed seeds, versioned datasets và tách validation/test để tránh overfitting vào benchmark.

## 6. Thiết kế dữ liệu ứng dụng (sau giai đoạn notebook)

```text
Identity & Goals
├── users
├── user_profiles
├── health_goals
└── goal_history

Body Data
├── body_measurement_sessions
├── anthropometric_measurements
├── body_composition_measurements
└── segmental_body_measurements

Document AI
├── inbody_documents
└── inbody_extraction_jobs

Computer Vision
├── body_images
└── image_analysis_jobs

Safety & Governance
├── medical_context_records
├── safety_assessments
├── consent_records
└── measurement_audit_logs

ML Intelligence
├── ml_predictions
├── model_versions
└── prediction_evaluations
```

### Provenance và trạng thái dữ liệu

- `declared`: Người dùng tự khai báo.
- `observed`: Kết quả thực đo hoặc kết quả thiết bị; cần ghi rõ phương pháp và thiết bị.
- `extracted`: Giá trị được OCR/parser trích xuất; cần người dùng xác nhận.
- `inferred`: Giá trị mô hình ML dự đoán; không được coi là đo trực tiếp.

Các trường khuyến nghị: `subject_id`, `measurement_session_id`, `measured_at`, `recorded_at`, `source`, `device_model`, `unit`, `verification_status`, `quality_flags`, `model_version`, `consent_id`, `audit_metadata`.

### Ví dụ JSON InBody đã chuẩn hóa

```json
{
  "source": "inbody",
  "device_model": "unknown",
  "measured_at": null,
  "weight_kg": null,
  "skeletal_muscle_mass_kg": null,
  "body_fat_mass_kg": null,
  "percent_body_fat": null,
  "total_body_water_l": null,
  "ecw_tbw_ratio": null,
  "basal_metabolic_rate_kcal": null,
  "verification_status": "pending_user_review"
}
```

Các giá trị `null` thể hiện trường chưa trích xuất hoặc chưa được xác minh, không được tự suy diễn.

## 7. Stack kỹ thuật

| Layer | Công nghệ đề xuất |
|---|---|
| Research | Python, JupyterLab / Colab |
| EDA | pandas, NumPy, matplotlib |
| OCR / Document AI | OpenCV, PaddleOCR, Hugging Face Transformers |
| Computer Vision | OpenCV, MediaPipe, PyTorch, torchvision, timm |
| Regression | scikit-learn, XGBoost |
| Experiments | MLflow, Optuna, DVC |
| API sau này | FastAPI, Docker |
| Storage sau này | PostgreSQL + Object Storage |

Không cần Kafka, Kubernetes hoặc streaming cho phiên bản nghiên cứu đầu tiên.

## 8. Kế hoạch triển khai theo phase

### Phase 1 — InBody Document AI (ưu tiên hiện tại)

- [ ] Khảo sát FUNSD/SROIE và phiếu InBody mẫu.
- [ ] Xác định field schema và annotation guideline.
- [ ] Thu thập/ghi nhãn tập phiếu được phép sử dụng.
- [ ] Xây dựng preprocessing và PaddleOCR baseline.
- [ ] Viết parser, normalization, validation và review flow.
- [ ] Benchmark OCR + rules so với layout-aware/VLM (nếu đủ dữ liệu).
- [ ] Báo cáo lỗi, metrics và giới hạn của dữ liệu.

**Deliverable:** Notebook, InBody JSON extraction pipeline, labeled benchmark, evaluation report.

**Cập nhật OCR:** [V6 + spatial extraction](docs/module_01/ocr_v6_spatial_extraction.md) đã tích hợp ở chế độ nghiên cứu,
giữ V5 đối chứng. Trên 16 phiếu giả lập, V5 + layout F1 0,902 và V6 + layout F1 0,803;
không coi hỗ trợ ngôn ngữ hay smoke test là đạt benchmark InBody thật. OCR trong app vẫn khóa.

### Phase 2 — Body Image Intelligence

- [x] Khám phá BodyM và giấy phép (nghiên cứu phi thương mại; đã ghi nhận bất nhất tên/link giấy phép).
- [x] Chuẩn hóa ảnh/silhouette và split theo người; kiểm tra toàn bộ 17.956 mask.
- [x] Tạo geometric features và baseline regression (Ridge metadata và silhouette + metadata).
- [x] Thử CNN/ViT khi có dữ liệu và tài nguyên phù hợp (đã chọn CNN hai view + metadata; chưa thử ViT).
- [x] Đánh giá MAE/RMSE, synthetic robustness và subgroup errors trên BodyM.

**Deliverable:** CV pipeline, baseline model, evaluation report.

**Kết quả triển khai:** [Phase 2](docs/module_01/phase_02_body_image_intelligence.md),
[evaluation report](experiments/bodym_phase2/report.md). Phạm vi là silhouette
BodyM; chưa kiểm chứng pose/segmentation ảnh RGB, ánh sáng/thiết bị điện thoại
hoặc độ chính xác sử dụng thực tế. Giữ nguyên checkpoint CNN đã chọn.

### Phase 3 — Multimodal ML

- [x] Thiết kế image/tabular encoders.
- [x] Thử fusion và ablation (tabular-only, image-only, fusion; cùng split theo người).
- [x] Calibration, uncertainty, out-of-distribution checks (323 người calibration độc lập trong lượt train mới; novelty heuristic).
- [x] Model card và reproducible training.

**Deliverable:** Fusion model và comparative experiments; chỉ thực hiện khi dữ liệu ghép cặp đủ chất lượng.

**Kết quả nghiên cứu:** [Phase 3](docs/module_01/phase_03_multimodal_ml.md),
[báo cáo](experiments/bodym_phase3/report.md), [model card](models/bodym_phase3/MODEL_CARD.md).
Default CNN giữ nguyên. Coverage joint của research fusion là 88,5%/81,0% trên
testA/testB ở mức danh nghĩa 90%; uncertainty deployment gate chưa đạt. Chưa có
external RGB/OOD benchmark hoặc test prospective mới; không coi đây là đủ điều kiện phát hành.

### Phase 4 — Body Progress Intelligence

- [x] Đồng bộ chuỗi thời gian các phép đo (offset/timezone, measured/recorded, as-of, phiên đo và audit).
- [x] Phân tích xu hướng, biến động và độ tin cậy (descriptive trends + quality/support gates; chưa có calibrated confidence/clinical validation).
- [x] Chuẩn bị dữ liệu cho Dashboard và AI Planner (subject-scoped JSON/schema, giữ nguồn, yêu cầu chọn stream khi mơ hồ).

**Deliverable:** Trend-analysis notebook, progress metrics.

**Kết quả nghiên cứu:** [Phase 4](docs/module_01/phase_04_body_progress_intelligence.md),
[báo cáo](experiments/body_progress_phase4/report.md), notebooks 14–16.
193 bản ghi giả lập/5 subject, không phải benchmark longitudinal thật. Không nội
suy, không trộn inferred/pending vào reviewed trend/Planner facts, không tự tạo
plan hoặc đổi goal. Các evaluation gates còn thiếu ở Phase 1/3 vẫn giữ nguyên.

### Phase 5 — Production Integration

- [x] Thiết kế DB, API và quyền truy cập (MVP local; PostgreSQL runtime chưa kiểm chứng).
- [x] Lưu nguồn phiếu có bảo vệ, mã hóa, xóa/retention/export (MVP; ảnh cơ thể chưa mở).
- [ ] Tích hợp OCR inference và user confirmation.
- [ ] Tích hợp CV inference khi mô hình đạt ngưỡng chất lượng đã định.
- [x] Áp dụng safety rules và consent management (wellness goal screening, chưa clinical validation).
- [x] Tạo end-to-end demo và monitoring (HTTP/browser local + process counters; chưa production alerting).

**Deliverable:** API, database, inference service, demo.

**Kết quả:** [Phase 5 local MVP](docs/module_01/phase_05_production_integration.md).
Review phiếu chép thủ công đã tích hợp; OCR inference, CV inference và production release
vẫn chờ các quality/security/native/deployment gates. Không coi MVP là đã đủ điều kiện phát hành.

## 9. Privacy, Safety & Evaluation Gates

- Chỉ thu thập dữ liệu sức khỏe/ảnh cơ thể khi có mục đích rõ ràng và đồng ý phù hợp.
- Consent cho xử lý cá nhân và consent cho sử dụng huấn luyện/nghiên cứu phải tách biệt.
- Tránh ảnh khỏa thân; hướng dẫn ảnh mặc trang phục phù hợp, có thể che mặt khi không cần nhận diện.
- Cho phép người dùng xem, sửa, tải xuống hoặc yêu cầu xóa dữ liệu theo chính sách áp dụng.
- Bảo vệ file nguồn, annotations và model artifacts khỏi rò rỉ thông tin cá nhân.
- OCR và ML phải có fallback khi confidence thấp; không phát hành số đo suy luận như sự thật đã đo.
- Quy tắc an toàn cần hoạt động độc lập với LLM; không đưa khuyến nghị chẩn đoán/điều trị.
- Báo cáo rõ giới hạn khi chuyển từ dataset nghiên cứu sang ảnh chụp thực tế.

## 10. Definition of Done

- [ ] Có tài liệu yêu cầu 8 features và JSON schema.
- [ ] Có dataset manifest, nguồn gốc và giấy phép.
- [ ] Có InBody OCR baseline, parser, validation và benchmark thực.
- [ ] Có quy trình user review trước khi lưu kết quả OCR.
- [ ] Có BodyM/body-image baseline và test theo người (nếu triển khai F04).
- [ ] Có multimodal ablation, uncertainty report (nếu đủ dữ liệu cho F08).
- [ ] Có trend analysis và phân biệt observed/extracted/inferred.
- [ ] Có reproducible notebooks, model versions và error analysis.
- [ ] Có privacy, consent và safety rules được thiết kế rõ.
- [ ] Có kế hoạch tích hợp backend, database và AI Weight Planner.

## 11. Thứ tự ưu tiên chốt

**Dataset → InBody Document AI → Body Image DL → Multimodal ML → Body Progress Analysis → Application Integration.**

**Bước làm ngay:** `01_ocr_dataset_exploration.ipynb`, sau đó chuẩn hóa InBody field schema và triển khai `03_ocr_baseline.ipynb` với PaddleOCR.
