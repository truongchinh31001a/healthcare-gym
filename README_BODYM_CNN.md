# BodyM: CNN tự thiết kế cho hai góc nhìn

Đây là **mô hình chính của dự án**, được chọn ngày 20/10/2026, học trực tiếp
từ hai silhouette và metadata để dự đoán vòng ngực, eo, hông (cm).
Lệnh dự đoán mặc định là `scripts/predict.py`, huấn luyện là `scripts/train.py`.

## Kiến trúc

```text
Ảnh trước [1,128,96] ──┐
                       ├─ CNN chung trọng số ── 128 đặc trưng mỗi ảnh ──┐
Ảnh nghiêng [1,128,96] ┘                                                │
                                                                       ├─ Ghép 272 ── 128 ── 64 ── 3
Chiều cao, cân nặng, giới tính ── MLP 3 → 32 → 16 ──────────────────────┘
```

Encoder ảnh có bốn khối `Conv3x3 → BatchNorm → ReLU → MaxPool2`, với số kênh
16/32/64/128, sau đó Global Average Pooling. Hai ảnh được đưa cùng encoder
trong một batch, giữ riêng thứ tự trước/nghiêng khi ghép đặc trưng. Dropout
0,2 đặt trong đầu dự đoán. Mô hình được khởi tạo ngẫu nhiên và học từ đầu.

Ảnh được nhị phân hóa, cắt theo bounding box của silhouette, thu nhỏ giữ nguyên
tỉ lệ và đặt giữa nền đen 128×96. Hai chiều không bị kéo giãn độc lập.

## Huấn luyện và đánh giá

- Dùng đúng danh sách 1.614 người fit / 404 người validation của Ridge.
- Chuẩn hóa metadata và nhãn từ người trong tập fit; mỗi người tính một lần.
- AdamW, Huber loss trên nhãn đã chuẩn hóa, cosine learning rate và gradient clipping.
- Trọng số mỗi cặp ảnh bằng nghịch đảo số cặp ảnh của người đó; mỗi người có tổng
  trọng số ngang nhau. MAE/RMSE cũng cân bằng theo người.
- Tối đa 60 epoch, early stopping sau 12 epoch không cải thiện validation MAE.
- Sau mỗi epoch, hiệu chuẩn lại thống kê BatchNorm bằng ảnh train ở trọng số
  cố định và độ chính xác FP32. Bước này không cập nhật trọng số hay dùng dữ liệu
  validation/test; nhằm giảm phụ thuộc vào các mini-batch cuối của epoch.
- Chọn epoch chỉ dựa trên validation. Khởi tạo lại và refit trên toàn bộ 2.018
  người train trong đúng số epoch đã chọn; giữ cùng lịch learning rate.
- Sau refit mới đánh giá `testA` và `testB` riêng. Hai tập test gốc chung 1 ID người.

Thiết lập nằm tại [configs/bodym_cnn.json](configs/bodym_cnn.json).

## Môi trường và lệnh chạy

Môi trường `.venv` của dự án dùng PyTorch CUDA 12.8 cho RTX 4060. Khi cài lại:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip install "torch==2.11.0+cu128" "torchvision==0.26.0+cu128" --index-url https://download.pytorch.org/whl/cu128
.venv/Scripts/python.exe -m pip install -r requirements-cnn.txt
```

Kiểm tra và chạy toàn bộ quy trình:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/run_bodym_cnn.py
```

Để chỉ xuất lại đánh giá từ checkpoint đã có, không huấn luyện lại:

```powershell
.venv/Scripts/python.exe scripts/run_bodym_cnn.py --evaluate-only
```

Có thể chọn `--device cpu` hoặc `--device cuda`; mặc định tự chọn CUDA nếu có.
Trước khi chạy, cần có dữ liệu BodyM và `configs/bodym_subject_split.json`.
Danh sách người này giữ nguyên cách chia đã dùng khi so sánh với Ridge.
Kết quả Ridge, nếu có, được thêm vào báo cáo để đối chiếu; CNN chạy độc lập.
Lần chạy sau dùng lại cache ảnh nếu dấu vân tay của CSV, manifest và thiết lập
tiền xử lý khớp.

## Kết quả lưu ra

- `models/bodym_cnn/model.pt`: trọng số cuối sau refit, thiết lập và thống kê chuẩn hóa.
- `models/bodym_cnn/architecture.txt`: cấu trúc PyTorch chi tiết.
- `experiments/bodym_cnn/selection_best.pt`: checkpoint chọn bằng validation, fit trên 1.614 người.
- `experiments/bodym_cnn/selection_history.json`, `refit_history.json`: lịch sử từng epoch.
- `experiments/bodym_cnn/metrics.json`: MAE/RMSE, cấu hình, phần cứng và so sánh Ridge.
- `experiments/bodym_cnn/*_predictions.csv`: nhãn thật và dự đoán từng cặp ảnh.
- `experiments/bodym_cnn/verification.json`: kiểm tra nạp lại checkpoint, tính lại MAE và inference ảnh gốc.
- `experiments/bodym_cnn/model_selection.json`: đối chiếu hai cách xử lý BatchNorm theo validation.
- `experiments/bodym_cnn/report.md`: báo cáo kèm biểu đồ.
- `data/processed/bodym/cnn_*_*.npz`: cache ảnh nhị phân, metadata, nhãn và ID.

Lần thử đầu chưa hiệu chuẩn BatchNorm được giữ tại
`experiments/bodym_cnn_initial/` và `models/bodym_cnn_initial/` để đối chiếu.

Notebook [09_multimodal_deep_learning.ipynb](notebooks/09_multimodal_deep_learning.ipynb)
hiển thị kiến trúc, kết quả và ví dụ dự đoán bằng mô hình đã lưu. Chọn kernel `.venv`.

## Dự đoán một cặp silhouette

```powershell
.venv/Scripts/python.exe scripts/predict_bodym_cnn.py --front path/to/front.png --side path/to/side.png --height-cm 170 --weight-kg 65 --gender male
```

Đầu vào là silhouette cơ thể đã tách nền, thứ tự trước/nghiêng giống BodyM.
Chiều cao, cân nặng và giới tính là dữ liệu đầu vào cần cung cấp.
Đầu ra gồm ba số đo theo cm. Kiến trúc này chưa có nhãn để học tỷ lệ mỡ hay khối lượng cơ.

## Kết quả lần chạy ngày 19/10/2026

Mô hình có **141.443 tham số**, huấn luyện từ đầu trên RTX 4060.
Chọn epoch 55 theo validation MAE **2,289 cm**, sau đó refit 55 epoch trên toàn bộ train.
Tổng thời gian các epoch chọn mô hình và refit khoảng 4,9 phút, chưa gồm cài môi trường
và tiền xử lý dữ liệu.

| Tập | Ngực MAE (cm) | Eo MAE (cm) | Hông MAE (cm) | Trung bình MAE (cm) |
| --- | ---: | ---: | ---: | ---: |
| testA | 2,342 | 2,270 | 1,519 | 2,043 |
| testB | 2,797 | 2,944 | 2,186 | 2,642 |

So với Ridge dùng silhouette + metadata, MAE trung bình giảm **9,0%** trên testA
và **12,6%** trên testB. Riêng vòng ngực testA có MAE cao hơn Ridge một chút
(2,342 so với 2,284 cm). Đây là kết quả của một seed, chưa phải kết luận thống kê
về mọi lần huấn luyện.

Hai biến thể được đối chiếu theo validation: BatchNorm ban đầu đạt 2,629 cm;
hiệu chuẩn BatchNorm chỉ bằng dữ liệu train đạt 2,289 cm và được giữ lại.
Checkpoint nạp lại, MAE tính độc lập, tiền xử lý ảnh gốc và notebook đều đã kiểm tra.
