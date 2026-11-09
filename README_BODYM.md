# BodyM dataset

Dữ liệu được lưu tại `data/raw/bodym/`, giữ nguyên cấu trúc của nguồn AWS:

```text
data/raw/bodym/
├── train/
├── testA/
├── testB/
│   ├── mask/
│   ├── mask_left/
│   ├── hwg_metadata.csv
│   ├── measurements.csv
│   └── subject_to_photo_map.csv
└── download_manifest.json
```

Cả ba tập đều có hai thư mục ảnh và ba file CSV như minh họa ở `testB`.

Số lượng kiểm tra trực tiếp từ file nguồn:

| Tập | Dòng người trong metadata | Cặp ảnh | File PNG |
| --- | ---: | ---: | ---: |
| train | 2.018 | 6.134 | 12.268 |
| testA | 87 | 1.684 | 3.368 |
| testB | 400 | 1.160 | 2.320 |
| Tổng | 2.505 | 8.978 | 17.956 |

Lưu ý: `testA` và `testB` có chung **1 `subject_id`** trong bảng gốc, nên
có **2.504 `subject_id` duy nhất** trên toàn bộ dữ liệu. `train` không trùng
người với hai tập test; không có `photo_id` trùng giữa các tập. Giữ kết quả
đánh giá `testA` và `testB` riêng biệt. Không tự ý sửa dữ liệu nguồn.

- `hwg_metadata.csv`: `subject_id`, `gender`, `height_cm`, `weight_kg`.
- `measurements.csv`: `subject_id` và 14 số đo theo cm: `ankle`,
  `arm-length`, `bicep`, `calf`, `chest`, `forearm`, `height`, `hip`,
  `leg-length`, `shoulder-breadth`, `shoulder-to-crotch`, `thigh`, `waist`, `wrist`.
- `subject_to_photo_map.csv`: ánh xạ `subject_id` sang `photo_id`.
  Dùng tên `<photo_id>.png` để tìm ảnh trong `mask/` và `mask_left/`.
  Một người có thể có nhiều cặp ảnh; không ghép CSV theo vị trí dòng.
- `download_manifest.json`: danh sách file nguồn, dung lượng, S3 ETag và thời điểm kiểm tra.

## Tải và kiểm tra

Chạy từ thư mục gốc dự án, chỉ cần Python 3, không cần AWS CLI hay tài khoản AWS:

```powershell
python scripts/download_bodym.py
```

Chạy lại sẽ kiểm tra checksum và chỉ tải lại file thiếu hoặc hỏng. Để kiểm tra
dữ liệu đã tải theo manifest mà không truy cập mạng:

```powershell
python scripts/download_bodym.py --verify-only
```

Nếu lần tải bị gián đoạn, có thể dùng `python scripts/download_bodym.py --resume`
để tiếp tục từ danh sách nguồn đã lưu, không cần liệt kê lại bucket.

## Sử dụng trong nghiên cứu

Mô hình chính là CNN hai góc nhìn kết hợp metadata; xem `README.md` và
`09_multimodal_deep_learning.ipynb` để huấn luyện, dự đoán và xem kết quả.
Các notebook trích xuất đặc trưng (`07`) và Ridge (`08`) phục vụ đối chiếu baseline.
Giữ nguyên `testA` và `testB` để đánh giá (`10`); nếu cần validation,
chia từ `train` theo `subject_id` để các ảnh của cùng một người nằm cùng tập.

BodyM cung cấp silhouette và số đo cơ thể. Bộ này không cung cấp phiếu InBody,
ảnh RGB gốc, nhãn tỷ lệ mỡ hay khối lượng cơ. Các notebook OCR InBody (`02–04`)
và mô hình cần những nhãn đó sẽ cần nguồn dữ liệu khác.

## Nguồn và điều kiện sử dụng

- Registry: https://registry.opendata.aws/bodym/
- Trang nghiên cứu: https://adversarialbodysim.github.io/
- Bài báo: *Human Body Measurement Estimation with Adversarial Augmentation* —
  Nataniel Ruiz, Miriam Bellver, Timo Bolkart, Ambuj Arora, Ming C. Lin,
  Javier Romero, Raja Bala.
- S3 bucket: `s3://amazon-bodym/`, vùng `us-west-2`.

Registry và trang nghiên cứu ghi tên giấy phép **Creative Commons
Attribution-Non Commercial 4.0**, nhưng đường dẫn giấy phép tại đó trỏ tới
CC BY 4.0. Hãy giữ lưu ý về sự không nhất quán này; dự án hiện sử dụng bộ dữ
liệu cho nghiên cứu phi thương mại và ghi nguồn. Cần xác minh với bên phát hành
trước khi sử dụng thương mại.

Các file dữ liệu tải về được loại khỏi Git bằng `.gitignore`.

## Kiểm tra cấu trúc dữ liệu

```powershell
python scripts/inspect_bodym.py
```

Lệnh này kiểm tra khóa ghép các bảng, ánh xạ file ảnh, số đo hữu hạn và dương,
và việc tập train không trùng người với các tập test. Lệnh cũng thống kê
`subject_id`/`photo_id` trùng giữa từng cặp tập. Báo cáo được lưu tại
`data/annotations/bodym_summary.json`.

## Chạy baseline dự đoán ngực, eo, hông

Môi trường hiện tại đã có `.venv`. Để chạy lại toàn bộ thí nghiệm:

```powershell
.venv/Scripts/python.exe scripts/run_bodym_baseline.py
```

Nếu thiết lập trên máy mới (Python 3.11):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/run_bodym_baseline.py
```

Baseline dùng 393 đặc trưng: chiều cao, cân nặng, giới tính và các profile
hình học từ hai silhouette. Script so sánh với giá trị trung bình tập train
và Ridge chỉ dùng metadata. Có 1.614 người để fit và 404 người validation;
chọn alpha trên validation rồi refit trên toàn bộ 2.018 người của train.
Các phép chuẩn hóa chỉ fit trên phần dữ liệu huấn luyện tương ứng.
Mỗi người có tổng trọng số bằng nhau khi fit và tính sai số, bất kể số cặp ảnh.

Kết quả được lưu tại:

- `experiments/bodym_baseline/report.md`: bảng MAE theo cm.
- `experiments/bodym_baseline/metrics.json`: MAE/RMSE, kết quả chọn alpha và phiên bản thư viện.
- `experiments/bodym_baseline/mae_comparison.png`: biểu đồ so sánh.
- `experiments/bodym_baseline/*_predictions.csv`: nhãn và dự đoán từng cặp ảnh.
- `experiments/bodym_baseline/subject_split.json`: danh sách người fit/validation.
- `models/bodym_baseline/ridge_models.pkl`: các mô hình đã fit và schema đặc trưng.
- `data/processed/bodym/*_features.npz`: đặc trưng, nhãn, subject/photo ID.

Mở `notebooks/08_body_measurement_baseline.ipynb` với Python trong `.venv`
để xem báo cáo và thử mô hình đã lưu. Mặc định notebook đọc kết quả hiện có;
đổi `RUN_TRAINING = True` nếu muốn huấn luyện lại.

Đây là baseline Ridge sử dụng cả metadata; chưa phải mô hình chỉ dùng ảnh
hay bản tái hiện BMnet. Trên lần chạy đầu, bổ sung silhouette giảm MAE trung
bình ở cả hai tập test, nhưng MAE vòng eo của testB tăng so với metadata-only.

## CNN tự thiết kế

Xem [README_BODYM_CNN.md](README_BODYM_CNN.md) cho kiến trúc hai góc nhìn,
thiết lập CUDA, cách huấn luyện và dự đoán bằng checkpoint CNN.

## Phase 2 — quality, subgroup và robustness

Xem [hướng dẫn Phase 2](docs/module_01/phase_02_body_image_intelligence.md) và
[báo cáo](experiments/bodym_phase2/report.md). Lượt này kiểm checksum/quality của
toàn bộ 17.956 mask, đánh giá lại CNN, tính lỗi theo nhóm và stress tests trên
mask gốc trước preprocessing. Model mặc định và các kết quả train được giữ nguyên.

Theo trang nghiên cứu BodyM, 14 số đo là số đo tính từ mesh đăng ký với 3D scan,
không phải nhãn thước dây hoặc InBody. Chưa có dữ liệu RGB để kiểm pose/segmentation.
