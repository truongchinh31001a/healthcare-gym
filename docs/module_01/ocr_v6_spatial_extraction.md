# PP-OCRv6 + trích xuất theo bố cục — nghiên cứu v1

Đã tích hợp PP-OCRv6_medium và bộ ghép nhãn–giá trị theo tọa độ. Config mặc định
`configs/inbody_ocr.json` trỏ đến ứng viên v6 + layout; **không phải model đã được duyệt phát hành**.
PP-OCRv5 English mobile được giữ làm đối chứng, có cả cấu hình gom hàng cũ và layout mới.

## Kết quả đo được

16 phiếu giả lập: 8 simple English cũ và 8 mẫu hai cột mới, gồm 4 mẫu tiếng Việt;
có ô thiếu kết quả, tham chiếu, dấu phẩy thập phân, EXIF xoay và blur nhẹ. 0 phiếu thật.
Không phải tập test lâm sàng hoặc heldout chưa từng xem. Không dùng annotation/template để định tuyến trích xuất.

| Pipeline | Precision giá trị | Recall giá trị | Field F1 | Mean CPU seconds |
|---|---:|---:|---:|---:|
| V5 + gom hàng | 1,000 | 0,507 | 0,673 | 5,57 |
| V5 + layout | 1,000 | 0,821 | **0,902** | 5,57 |
| V6 + gom hàng | 1,000 | 0,507 | 0,673 | 20,11 |
| V6 + layout | 1,000 | 0,671 | **0,803** | 20,11 |

Thời gian là preprocessing + inference + parsing trên CPU/4 threads, không gồm startup/download model
và không phải phép đo điện thoại hoặc SLA production. Một lượt inference/model/ảnh, dùng cùng tokens
cho hai phương pháp ghép trường. Null/null không tính là field true positive. Exact document chỉ 8/16
cho cả bốn cấu hình; precision cao không có nghĩa tất cả trường được đọc đúng/đủ.

**Kết luận thực nghiệm:** layout giúp cải thiện việc ghép trường; v6 chưa thắng v5 trên tập này.
V6 có nhãn tiếng Việt mất ký tự dù confidence cao; bbox chữ nhỏ hơn cũng khiến quy tắc khoảng cách
bảo thủ từ chối thêm liên kết. Không thêm alias lỗi hoặc nới ngưỡng để làm đẹp điểm test.
V5 + layout là cấu hình đối chứng nên dùng khi cần so sánh tiếp; chưa có cấu hình nào đủ bằng chứng
để mở cho người dùng thật. Giữ v6 là ứng viên nghiên cứu đúng yêu cầu, không tự promote theo tên phiên bản.

[Báo cáo chi tiết](../../experiments/inbody_ocr_comparison_v1/report.md),
[metrics và lỗi từng field/nhóm](../../experiments/inbody_ocr_comparison_v1/metrics.json),
[notebook 17](../../notebooks/17_inbody_spatial_ocr_comparison.ipynb).

Kiểm tra triển khai: **29/29 tests qua**, notebook 03 và 17 đã thực thi không có lỗi cell.
Lệnh CLI mặc định V6 đã chạy thật trên một phiếu tiếng Anh giả lập, trích 9/9 trường;
record xác nhận tạo riêng, draft vẫn pending và provenance vẫn extracted. Điều này không
thay thế kết quả so sánh 16 phiếu hoặc đánh giá phiếu thật.

## Cách hoạt động

- Tiền xử lý hiện tại giữ toàn trang, EXIF transpose, grayscale/autocontrast và giới hạn size/pages/pixels.
  Chưa tự sửa perspective/dewarp/blur; hai model dùng cùng preprocessing để so sánh.
- OCR trả nguyên text, bbox, page và confidence. Không coi confidence là xác suất số liệu đúng.
- Nhận diện nhãn theo aliases đã có, tách tại nhãn khác trên cùng hàng; chặn khoảng cách quá xa và
  loại phần sau nhãn tham chiếu rõ ràng. Không chọn gần nhất trong nhiều giá trị có thể là kết quả.
- Giữ null khi label sai/mất, unit thiếu, nhiều số, nhiều nhãn trùng hoặc không ghép chắc chắn.
- Template tùy chọn chứa ROI nhãn/value chuẩn hóa theo trang; cần chọn tay sau khi đối chiếu mẫu thật.
  Hiện **chưa đăng ký template của máy InBody thật**. Tokens cắt qua ROI hoặc được dùng cho hai trường
  bị từ chối, không bịa đơn vị hoặc cắt nội dung một box để lấy số.
- Giữ `extraction.json` đúng schema cũ và `pending_user_review`. `layout.json` là sidecar chứa phiên bản
  spatial parser, box/token IDs, text gốc/canonical và lý do loại bỏ. `provenance.json` gắn source/model/config hash.
- Đối chiếu, chọn trường, sửa/acknowledge flags qua `confirm_fields`; giữ provenance `extracted`, không đổi thành observed.

## Chạy lại

Dùng môi trường CPU `.venv-ocr`, không cài Paddle đè môi trường BodyM CUDA:

```powershell
.venv-ocr/Scripts/python.exe scripts/prepare_inbody_layout_synthetic.py
.venv-ocr/Scripts/python.exe scripts/compare_inbody_ocr.py
.venv-ocr/Scripts/python.exe -m unittest tests.test_inbody_document_ai tests.test_inbody_layout -q
```

Generator dùng font TrueType tiếng Việt; mặc định Arial của Windows. Có thể truyền `--font` với đường dẫn
font phù hợp trên máy khác; hash font được lưu trong manifest, đổi font có thể đổi pixel/kết quả.

Chạy một phiếu bằng v6 + layout (đây vẫn là research CLI):

```powershell
.venv-ocr/Scripts/python.exe scripts/run_inbody_ocr.py --input path/to/report.png
```

So sánh cùng phiếu bằng v5 + layout:

```powershell
.venv-ocr/Scripts/python.exe scripts/run_inbody_ocr.py --input path/to/report.png --config configs/inbody_ocr_v5_layout.json
```

`--input` ghi tại thư mục Git-ignored `data/processed/inbody_private/<source-hash>/<experiment>/<template>/`;
đây là file nghiên cứu cục bộ, **chưa có auth/mã hóa/retention production của app**. Không đưa phiếu thật
vào public benchmark/notebook output. Public comparison từ chối manifest có sample không được đánh dấu synthetic.
Các artefact Phase 1 cũ được giữ nguyên; notebook 03 dùng config lịch sử riêng để tái lập baseline.

Ví dụ cấu trúc template tự khai báo trong `configs/inbody_layout.json` (tọa độ chỉ minh họa, không dùng làm
mẫu InBody thật):

```json
{"templates": {"verified-local-v1": {"fields": {"weight_kg": {
  "page": 0, "label_box": [0.03, 0.20, 0.30, 0.25], "value_box": [0.32, 0.20, 0.45, 0.25]
}}}}}
```

Sau khi kiểm tra tọa độ của chính mẫu được phép dùng, truyền `--template verified-local-v1`.
Không tự chọn template từ nhãn ground truth; chọn sai template vẫn có thể làm sai association.

## Điều kiện tiếp theo

Thu thập khoảng 100–200 phiếu thật được phép dùng làm pilot; gán nhãn số, đơn vị, ngày và bbox kết quả/tham chiếu.
Chia theo người/phiếu gốc, có holdout layout/thiết bị. Đánh giá bỏ sót/sai số, false extraction, field/date/unit exact,
latency và thời gian sửa từ người đối chiếu. Khảo sát lỗi trước khi cân nhắc PP-StructureV3/fine-tuning.
Mức 100–200 là kế hoạch pilot, không đảm bảo đủ bằng chứng phát hành.

OCR trong app vẫn khóa và CNN BodyM không thay đổi. API đang chạy tiếp tục dùng luồng chép/đối chiếu thủ công.

Nguồn thuật toán: [PaddleOCR v6](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html),
[PP-StructureV3](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html).
Hỗ trợ ngôn ngữ/benchmark công bố của model không thay thế đánh giá phiếu InBody của dự án.
