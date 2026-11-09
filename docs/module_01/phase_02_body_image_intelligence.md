# Phase 2 — Body Image Intelligence

Triển khai nghiên cứu **silhouette BodyM** theo Module 01, dùng CNN hai góc nhìn
đã chọn. Phase này không train lại hay thay model mặc định. Bộ dữ liệu đã tách
nền, vì vậy không thể dùng nó để chứng minh pose estimation/segmentation ảnh RGB.

## 1. Dataset và provenance

- Đối chiếu [AWS Registry](https://registry.opendata.aws/bodym/) và
  [trang nghiên cứu](https://adversarialbodysim.github.io/).
- Nhãn chu vi/chiều dài được tính từ mesh đăng ký với 3D scan; không phải phiếu
  InBody hoặc số đo thước dây. Metadata gồm chiều cao, cân nặng, giới tính được cung cấp.
- 2.018 người train, 87 người testA, 400 người testB; 8.978 cặp/17.956 ảnh.
  1.614 fit + 404 validation giữ nguyên từ cấu hình đã chốt. testA/testB có 1 ID
  chung, luôn báo riêng. Không có người train trong hai test.
- Mỗi PNG và CSV được so size/ETag với manifest tải gốc. Manifest Phase 2 thêm
  SHA256 CSV, inventory ảnh, audit và danh sách split để truy vết.
- Registry và trang nghiên cứu ghi tên **BY-NC 4.0**, nhưng link sang BY 4.0.
  Hiện chỉ nghiên cứu phi thương mại, cần làm rõ trước dùng thương mại.

Manifest: `data/manifests/bodym_phase2_v1.json`.
Audit từng ảnh: `data/processed/bodym_phase2/quality_audit.jsonl` (không Git).

## 2. Quality checks và preprocessing

`src/body_vision/quality.py` kiểm mask rỗng/full, foreground có độ phân giải thấp,
pixel không nhị phân, foreground chạm khung và thành phần rời nhau. Các ngưỡng
kỹ thuật cố định trong `configs/bodym_phase2.json`, không chọn từ test.

Cờ lỗi giữ nguyên trong audit, **không tự loại ảnh khỏi đánh giá toàn bộ test**.
Chạm khung có thể là capture/crop hợp lệ; một mask vượt mọi kiểm tra vẫn có thể
sai tư thế. Chưa có keypoint/nhãn pose để đo chất lượng giải phẫu.

Canonical preprocessing giữ đúng checkpoint: threshold >127 → bounding box →
resize giữ tỷ lệ → letterbox 128×96, padding 4. Đọc ảnh gốc, không ghi đè nguồn.

Notebook: `06_bodym_dataset_exploration.ipynb`, `07_body_image_preprocessing.ipynb`.
Hai placeholder `05_body_pose_estimation`/`06_body_segmentation` dành cho nguồn RGB
sau này; không tạo keypoint/segmentation giả từ dữ liệu chưa có.

## 3. Geometric features và baseline

Giữ thuật toán đã có ở `scripts/run_bodym_baseline.py`:

- 64 bins theo chiều cao cho span, occupied width, center; 3 scalar/view.
- 195 features/view × 2 + 3 metadata = 393 features.
- Chest/waist/hip là nhãn `y`, không dùng làm input `X`.
- Ridge metadata-only và silhouette+metadata là baseline so sánh. Phase 2 đọc
  predictions đã lưu, kiểm IDs và nhãn so với dataset rồi tính lại MAE/RMSE.

Notebook `07_body_feature_extraction.ipynb` đã được điền và thực thi; notebook 08
giữ kết quả baseline trước đó. Chưa triển khai XGBoost/ViT hay ablation image-only
ở lượt này; không cần các mô hình đó để xác nhận baseline/CNN hiện có.

## 4. CNN và đánh giá

CNN chính: shared Conv16/32/64/128 + GAP, metadata MLP và fusion head,
141.443 tham số; checkpoint `models/bodym_cnn/model.pt`.

- Nạp checkpoint và suy luận lại đầy đủ testA/testB, không optimizer/training.
- Kiểm normalization checkpoint khớp unique subjects của train; kiểm version
  preprocessing, labels, split isolation và hash checkpoint trước/sau chạy.
- MAE/RMSE/bias từng chu vi, cân bằng theo người dù một người có nhiều ảnh.
- Subgroup theo giới tính cung cấp và BMI quartiles **chỉ fit trên 1.614 FIT
  subjects**; nhóm <20 người được gắn cờ. Không phải phân loại sức khỏe/fairness audit.
- Cờ nằm ngoài min/max chiều cao/cân nặng FIT chỉ mô tả phạm vi, chưa phải OOD detector.

Kết quả tại `experiments/bodym_phase2/report.md`, `metrics.json`, `evaluation.png`.
Notebook `10_model_evaluation.ipynb` kiểm lại metrics từ dự đoán, đọc report và biểu đồ.

## 5. Robustness có kiểm soát

Một cặp/người, tối đa 128 người/test split; chọn bằng seed 42 và ảnh đầu theo ID,
không chọn bằng nhãn/lỗi. Có 87 người testA và 128 người testB trong stress subset.

Biến dạng trên **mask gốc trước preprocessing**:

| Thử nghiệm | Mục đích |
|---|---|
| Identity | Kiểm bit-for-bit preprocessing với cache |
| Translation có padding | Kiểm bbox normalization bất biến tịnh tiến, không clipping/wrap |
| Erode/dilate 2 px | Độ nhạy với sai lệch biên segmentation |
| Rotate 5° | Stress do xoay mặt phẳng ảnh, không tương đương thay đổi pose 3D |
| Remove top 10% foreground height | Stress mất phần cơ thể; không chứng minh detector nhận ra lỗi |

Delta MAE so với clean **cùng subset**, không so trực tiếp với full-test MAE.
Lưu số người attempted/retained/rejected, không ẩn trường hợp preprocessing thất bại.
Nhãn cơ thể giữ nguyên dưới biến dạng nhân tạo. Không dùng kết quả stress để
tune model sau khi xem test. Không có đánh giá ánh sáng, thiết bị hoặc camera RGB.

## Chạy lại

Dùng môi trường `.venv` BodyM CUDA đã có, **không dùng `.venv-ocr`**:

```powershell
.venv/Scripts/python.exe scripts/run_bodym_phase2.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_body_vision_phase2.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_bodym_cnn.py -v
.venv/Scripts/python.exe -m ipykernel install --user --name bodym-research --display-name "Python (BodyM Research)"
.venv/Scripts/python.exe scripts/execute_bodym_phase2_notebooks.py
```

Có thể thêm `--device cpu` nếu không có CUDA. Cấu hình tại
`configs/bodym_phase2.json`; source/CNN dependencies giữ trong `requirements.txt`
và `requirements-cnn.txt`. Lệnh sẽ kiểm toàn bộ dữ liệu nguồn trước suy luận.
Sau khi đã có audit đầy đủ, `--reuse-audit` vẫn tính lại SHA256 toàn bộ ảnh/CSV,
kiểm checksum audit/config/split và chỉ bỏ qua bước phân tích connected components.
Script tạo notebook chỉ dùng lúc khởi tạo và từ chối ghi đè notebook đã có nội dung.

## Evaluation gates còn lại

Phạm vi nghiên cứu silhouette Phase 2 có dataset audit, CV preprocessing, geometric
baseline, CNN và báo cáo lỗi/subgroups/synthetic stress. Chưa sẵn sàng cho đo cơ
thể bằng ảnh điện thoại: cần RGB được cấp quyền và consent, hướng dẫn chụp, nhãn
ghép cặp, pose/segmentation và test ngoài miền dữ liệu. Không dự đoán mỡ/cơ/InBody.

**Phase 3 tiếp theo:** ablations tabular/image/fusion với cùng split; hiệu chuẩn
uncertainty chỉ bằng validation, đánh giá interval coverage/OOD và model card.
Backend/API/mobile review và consent store thuộc giai đoạn tích hợp sau nghiên cứu.
