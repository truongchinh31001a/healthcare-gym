# Phase 3 — Multimodal ML, ablation và uncertainty

Tiếp tục theo Module 01: train image/tabular/fusion với cùng split, hiệu chuẩn
khoảng dự đoán trên người không tham gia các bước fit/chọn epoch mới, kiểm novelty
và viết model card. Model mặc định đã chốt ở Phase 2 được giữ nguyên.

## 1. Vì sao cần checkpoint nghiên cứu mới?

Checkpoint mặc định `models/bodym_cnn/model.pt` đã refit trên toàn bộ 2.018 người
train, bao gồm 404 người validation cũ. Không thể dùng residual của những người
đó để hiệu chuẩn khoảng dự đoán cho chính checkpoint này như dữ liệu chưa thấy.

Protocol nghiên cứu mới (seed split 20261022):

| Nhóm | Số người | Vai trò |
|---|---:|---|
| Proper fit | 1.291 | Train chọn epoch, normalization và BatchNorm giai đoạn selection; fit novelty |
| Tuning | 404 | Chọn epoch từng biến thể; giữ nguyên nhóm validation trước đó |
| Calibration | 323 | Chỉ tính residual/radius sau khi khóa checkpoint mới |
| Refit | 1.695 | Proper fit + tuning, train lại đúng số epoch đã chọn |
| testA / testB | 87 / 400 | Đánh giá riêng, giữ nguyên dataset gốc |

Calibration được lấy từ nhóm fit 1.614 người ban đầu bằng seed cố định. Ba nhóm
mới không trùng người; cộng lại đúng original train. Norm target/metadata và BN
của model refit chỉ dùng 1.695 người. Không refit trên calibration sau khi tạo radius.

Lưu ý nghiên cứu: dữ liệu, kiến trúc/hyperparameters và các test đã được khảo sát
trong phase trước. Chia lại và train mới ngăn leakage trực tiếp trong lượt này,
nhưng không biến dataset thành benchmark prospective chưa từng xem. Cần dữ liệu
mới trước khẳng định bảo đảm tổng quát hóa.

## 2. Ablation có huấn luyện riêng

| Variant | Input và nhánh |
|---|---|
| tabular_only | Height/weight/provided gender → MLP; không image encoder |
| image_only | Hai silhouette → shared CNN; không metadata encoder |
| fusion | Hai silhouette + metadata, concat features → regression head |

Hai nhánh dùng cấu hình kiến trúc tương ứng CNN đã chọn; head có cùng hidden
widths. Mỗi model khởi tạo mới, seed 42, cùng optimizer/lịch LR/loss/weight theo
người, max 60 epochs và patience 12. Epoch được chọn theo tuning MAE, không theo
calibration/test. Refit replay lịch LR đến epoch đã chọn.

Không chỉ zero input trong model fusion để gọi là ablation. Chu vi chest/waist/hip
chỉ là nhãn y. Chưa có XGBoost/ViT hoặc nhiều seed trong lượt này.

## 3. Khoảng dự đoán theo người

Phương pháp: absolute-residual split conformal, danh nghĩa 90%, có hiệu chỉnh
finite-sample theo [Angelopoulos & Bates](https://arxiv.org/abs/2107.07511).

1. Mỗi người calibration đóng góp một score/target = lỗi tuyệt đối lớn nhất qua
   các cặp ảnh của người đó. Không coi các ảnh cùng người là mẫu độc lập.
2. Radius mỗi target là score đứng thứ `ceil((n+1)*(1-alpha))`, đánh số từ 1.
   Nếu quá ít người để có radius hữu hạn thì báo lỗi, không dùng quantile thấp hơn.
3. Joint score lấy max qua cả ba target; joint radius tạo box bao phủ đồng thời.
4. Báo per-target/all-photo subject coverage, joint coverage, subject-balanced
   pair coverage và full interval widths. Không trộn per-target với simultaneous coverage.

Các khoảng có radius cố định theo model/target, chưa phải adaptive/heteroscedastic
intervals. Coverage cần exchangeability của các subject bundles và predictor độc
lập với calibration. Capture domain và số ảnh/người khác nhau có thể làm giả định
không thỏa, đặc biệt testA nhiều ảnh/người hơn. Mức 90% danh nghĩa không phải xác
suất đúng cho cá nhân hay tolerance y khoa. Luôn đọc coverage cùng width.

Calibrator ghi SHA256 đúng checkpoint, split hash và target schema; loader từ chối
calibrator/model khác nhau. Không áp dụng radius mới cho default checkpoint.

## 4. Novelty/OOD heuristic

19 features: height/weight/provided gender + 8 đặc trưng mỗi view (bbox aspect,
fill và 6 width spans). Median/IQR và threshold 99% chỉ fit trên một ảnh cố định
mỗi proper-fit subject. Thêm cờ metadata ngoài min/max proper fit.

Không dùng label/calibration/test để chọn threshold. Đây là heuristic phát hiện
phạm vi dữ liệu, không phải OOD classifier đã benchmark hoặc xác suất an toàn.
Chưa có OOD ground truth nên không báo AUROC/sensitivity/specificity. Cờ không
loại trường hợp khỏi overall test metrics; xem thêm flagged/unflagged strata.

## 5. Artifacts và notebook

- `experiments/bodym_phase3/subject_split.json`: danh sách người theo protocol mới.
- `experiments/bodym_phase3/metrics.json`, `report.md`, `comparison.png`: kết quả.
- `experiments/bodym_phase3/<variant>/`: selection/refit histories và epoch selection.
- `models/bodym_phase3/<variant>/model.pt`, `calibration.json`: checkpoint/radius gắn cặp.
- `models/bodym_phase3/novelty.json`, `MODEL_CARD.md`: detector heuristic và model card.
- `data/processed/bodym_phase3/<variant>/*_predictions.npz`: dự đoán/nhãn/IDs/cờ, không Git.
- Notebooks 11: ablation; 12: uncertainty; 13: novelty, inference demo và model card.

## Chạy lại

Dùng `.venv` BodyM CUDA, không cài thêm dependency mới:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_multimodal_phase3.py -v

# Chỉ chạy training khi chưa có checkpoint ở model_dir của experiment.
.venv/Scripts/python.exe scripts/run_bodym_phase3.py

# Khi đã có artifacts: tính lại test metrics, không train hoặc recalibrate.
.venv/Scripts/python.exe scripts/run_bodym_phase3.py --evaluate-only
.venv/Scripts/python.exe scripts/execute_bodym_phase3_notebooks.py
```

Training từ chối ghi đè checkpoint hoàn tất. Muốn thí nghiệm mới, sao chép config
với `output` và `model_dir` mới rồi truyền `--config`. Không dùng calibration/test
để chọn tham số sau khi đã đọc kết quả. Có thể thêm `--device cpu`.

Suy luận research fusion riêng (không đổi `scripts/predict.py` mặc định):

```powershell
.venv/Scripts/python.exe scripts/predict_bodym_phase3.py --front path/front.png --side path/side.png --height-cm 170 --weight-kg 65 --gender male
```

CLI yêu cầu silhouette grayscale đã tách nền, đúng thứ tự front/side. Trả point,
per-target/joint intervals, provenance `inferred`, trạng thái chưa xác minh,
quality/novelty flags và `research_only`. Không tự lưu observation vào ứng dụng.
Ảnh RGB chưa hỗ trợ. Model card mô tả intended use, giới hạn dữ liệu và evaluation gates.

Notebook 13 kiểm tra raw/cache bằng cùng backend CPU (tolerance 1e-6 cm), đồng thời
ghi chênh lệch so với artifact GPU/batched. Ở mẫu đầu testB, raw/cache CPU trùng
nhau; chênh lệch CPU so với GPU khoảng 0,0025 cm. Không yêu cầu bitwise equality
giữa các backend; CUDA cuDNN TF32 được bật trong lần GPU đã ghi nhận.

## Phần chưa đạt điều kiện phát hành

Chưa có nhiều seed, RGB/phone evaluation, nhãn OOD, external prospective test,
ngưỡng lỗi chấp nhận đã thống nhất hoặc privacy/safety application integration.
BodyM chỉ phục vụ nghiên cứu phi thương mại khi tên/link giấy phép còn bất nhất.

Lần chạy này fusion đạt joint all-photo subject coverage **88,5% testA / 81,0%
testB**, thấp hơn mức danh nghĩa 90%; joint interval rộng khoảng **14,864 cm**.
Vì vậy evaluation gate cho uncertainty **chưa qua**. Không chọn radius lại từ
test; cần calibration đại diện hơn hoặc phương pháp khác được chọn bằng dữ
liệu phát triển, rồi kiểm trên test mới. Unflagged novelty không chứng minh an toàn.

Phase 4 tiếp theo: temporal alignment, data-quality checks, trend/change analysis
và phân biệt rõ observed/extracted/inferred khi tạo progress metrics.
