# Healthcare AI Research

Module 01 đang được phát triển theo thứ tự trong
[đặc tả](Module_01_User_and_Body_Profile.md). Bắt đầu tại
[hướng dẫn triển khai từng bước](docs/module_01/README.md): dataset/schema →
InBody OCR → validation/review → benchmark thật → tích hợp ứng dụng.
Notebook đầu: [01 — OCR dataset exploration](notebooks/01_ocr_dataset_exploration.ipynb).
Môi trường OCR riêng: `.venv-ocr`; phiếu thử là dữ liệu giả lập, chưa có benchmark InBody thật.

OCR hiện đã có [PP-OCRv6 + ghép trường theo bố cục](docs/module_01/ocr_v6_spatial_extraction.md),
[so sánh 2×2](experiments/inbody_ocr_comparison_v1/report.md) và
[notebook 17](notebooks/17_inbody_spatial_ocr_comparison.ipynb). V6 là ứng viên nghiên cứu;
V5 + layout đang tốt hơn trên 16 phiếu giả lập, chưa có độ chính xác phiếu thật.

Phase 2: [Body Image Intelligence](docs/module_01/phase_02_body_image_intelligence.md)
và [báo cáo đánh giá](experiments/bodym_phase2/report.md), gồm kiểm tra toàn bộ
silhouette, lỗi theo nhóm và synthetic robustness. Chạy bằng `.venv` BodyM.

Phase 3: [Multimodal ablation & uncertainty](docs/module_01/phase_03_multimodal_ml.md),
[báo cáo](experiments/bodym_phase3/report.md) và [model card](models/bodym_phase3/MODEL_CARD.md).
Các checkpoint nghiên cứu riêng có calibration holdout; model mặc định bên dưới giữ nguyên.

Phase 4: [Body Progress Intelligence](docs/module_01/phase_04_body_progress_intelligence.md)
và [báo cáo](experiments/body_progress_phase4/report.md): căn chỉnh lịch sử đo,
quality/trend analysis và JSON/schema cho Dashboard/Planner; thử bằng dữ liệu giả lập.

Phase 5: [Application integration MVP](docs/module_01/phase_05_production_integration.md)
và [hướng dẫn chạy app/API/web](ai-personal-health-assistant/README.md). Có auth, consent,
hồ sơ, số đo, review phiếu, progress và goal screening; OCR/CV production vẫn khóa.

Mô hình chính của dự án là **CNN hai góc nhìn kết hợp metadata**,
được chọn ngày 20/10/2026. Cấu hình mặc định nằm tại
[configs/default_model.json](configs/default_model.json).

Đầu vào: hai silhouette trước/nghiêng, chiều cao (cm), cân nặng (kg), giới tính.
Đầu ra: vòng ngực, eo, hông theo cm. CNN có 141.443 tham số, học từ đầu;
checkpoint hiện tại đã refit trên toàn bộ 2.018 người train trong 55 epoch.

## Dự đoán bằng mô hình mặc định

Môi trường `.venv` và checkpoint đã sẵn sàng trong workspace hiện tại:

```powershell
.venv/Scripts/python.exe scripts/predict.py --front path/to/front.png --side path/to/side.png --height-cm 170 --weight-kg 65 --gender male
```

Ảnh đầu vào là silhouette người màu trắng trên nền đen, cùng cách biểu diễn
của BodyM. Mở [notebook CNN](notebooks/09_multimodal_deep_learning.ipynb)
để chạy ví dụ với ảnh thật từ dataset và xem kết quả đã thực thi.

## Huấn luyện và đánh giá

```powershell
.venv/Scripts/python.exe scripts/train.py
```

Lệnh này chọn epoch trên 1.614 người fit / 404 người validation, rồi refit trên
toàn bộ train. Danh sách người được cố định tại
[configs/bodym_subject_split.json](configs/bodym_subject_split.json).
Ridge là mô hình tham chiếu để so sánh, không bắt buộc phải chạy trước CNN.

Để xuất lại đánh giá từ checkpoint hiện có:

```powershell
.venv/Scripts/python.exe scripts/train.py --evaluate-only
```

## Kết quả đã ghi nhận

MAE trung bình theo người của ba số đo, đơn vị cm:

| Tập test | Ridge tham chiếu | CNN chính |
| --- | ---: | ---: |
| testA | 2,246 | 2,043 |
| testB | 3,023 | 2,642 |

Xem [báo cáo](experiments/bodym_cnn/report.md) và
[hướng dẫn CNN](README_BODYM_CNN.md) để biết kiến trúc, cài CUDA,
kiểm tra mô hình và giới hạn của lần chạy. Dữ liệu BodyM được mô tả trong
[README_BODYM.md](README_BODYM.md).

Checkpoint chính: `models/bodym_cnn/model.pt`.
Các kết quả Ridge và CNN thử nghiệm ban đầu được giữ để đối chiếu nghiên cứu.
