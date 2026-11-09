# Phân tích lỗi OCR hiện tại

Phân tích ngày 2026-10-22 từ `experiments/inbody_ocr_comparison_v1/metrics.json`,
annotation trong manifest `inbody_layout_synthetic_v1.json` và cache token/layout tương ứng.
Không chạy lại model, không thay config, không điều chỉnh parser theo nhãn test.

## Kết luận

Điểm nghẽn quan sát được nằm ở nhận diện nhãn và ghép nhãn–giá trị theo bố cục.
V5 + layout tốt nhất trong bốn pipeline đã thử, nhưng chưa có bằng chứng chất lượng
trên phiếu thật. V6 vẫn là ứng viên nghiên cứu trong config mặc định, chưa được duyệt
đưa vào app. Mô hình CNN BodyM không liên quan đến nhận dạng phiếu.

## Kết quả đã đo

16 ảnh giả lập, 140 giá trị có nhãn; 12 ảnh tiếng Anh và 4 ảnh tiếng Việt.
Hai model dùng cùng tiền xử lý; mỗi model chạy một lần mỗi ảnh, rồi hai parser
tiêu thụ cùng tập token của model đó. Đây là so sánh pipeline, không cô lập riêng
chất lượng recognition: detector và recognizer đều thay giữa V5 và V6.

| Pipeline | Giá trị đúng/có nhãn | Bỏ sót | Field F1 | Thời gian CPU trung bình |
|---|---:|---:|---:|---:|
| V5 + gom hàng | 71/140 | 69 | 0,673 | 5,57 giây |
| V5 + layout | 115/140 | 25 | 0,902 | 5,57 giây |
| V6 + gom hàng | 71/140 | 69 | 0,673 | 20,11 giây |
| V6 + layout | 94/140 | 46 | 0,803 | 20,11 giây |

Không ghi nhận giá trị sai hoặc trích dư trong lần thử này; precision 1,0 chỉ áp
dụng cho các giá trị đã xuất. MAE bằng 0 trên các cặp có giá trị không phản ánh
các trường bỏ sót. Cả bốn cấu hình chỉ đạt đúng toàn phiếu 8/16; đó là tám mẫu
simple-row cũ. Thời gian CPU/4 threads không gồm nạp model và tải trọng số.

| Nhóm | V5 + layout F1 | V6 + layout F1 |
|---|---:|---:|
| Tiếng Anh, 12 ảnh | 0,981 | 0,934 |
| Tiếng Việt, 4 ảnh | 0,571 | 0,108 |
| Một cột đơn giản, 8 ảnh | 1,000 | 1,000 |
| Hai cột, 8 ảnh | 0,779 | 0,500 |

Nhóm ngôn ngữ và nhóm bố cục chồng lấp; không coi đây là các thí nghiệm độc lập.
Tập tiếng Việt chỉ có bốn ảnh nên chưa đủ kết luận tổng quát về ngôn ngữ.

## Hai nhóm lỗi quan sát được

Phân loại từng trường có ground truth nhưng đầu ra null: nếu không có entry cho
field trong layout sidecar thì ghi nhận thiếu label anchor; nếu có entry với
`large_horizontal_gap` thì ghi nhận từ chối khoảng cách. Đây là phân loại theo
dấu vết chương trình, không phải khẳng định nguyên nhân gốc đã được cô lập.

| Dấu vết ở trường bỏ sót | V5 + layout | V6 + layout |
|---|---:|---:|
| Không có label anchor được nhận diện | 13 | 25 |
| Có anchor nhưng từ chối khoảng cách | 12 | 21 |
| Tổng | 25 | 46 |

**Nhãn tiếng Việt:** ở `layout-synthetic-004`, V6 đọc “Cân nng:” và “Chiu cao:”,
với confidence lần lượt khoảng 0,9993 và 0,9999. Bộ ghép yêu cầu alias hợp lệ
nên không liên kết các nhãn này với cân nặng/chiều cao, dù số 74 kg và 174 cm
đã được OCR nhận diện. Confidence OCR không phải xác suất field đúng; tăng ngưỡng
confidence không giải quyết được ví dụ này.

**Khoảng cách phụ thuộc bbox:** với `layout-synthetic-000`, nhãn Weight của V6
có chiều cao 29 px; khoảng trống đến giá trị xấp xỉ 310 px, vượt ngưỡng hiện tại
10 lần chiều cao nhỏ hơn của hai box. V5 tạo box nhãn cao 37 px, nên cùng liên
kết này đi qua. Đây là một ví dụ trực tiếp cho thấy hình học bbox ảnh hưởng
recall mà không cần có lỗi đọc số.

ECW/TBW chỉ lấy được 8/16 trường với cả V5 và V6 + layout; cả tám mẫu hai cột
đều mất trường này. Chưa có template của máy InBody thật được đăng ký.

## Thứ tự cải thiện đề xuất

1. **Đối chứng ngôn ngữ đúng mục tiêu.** Baseline V5 hiện dùng
   `en_PP-OCRv5_mobile_rec`, một model tiếng Anh. Thử thêm recognizer V5 cho
   tiếng Việt/Latin, đối chiếu với V6 trên cùng input. Khi cần phân tích riêng
   recognition, cố định detector và crop để giảm biến gây nhiễu. Không diễn
   giải chiến thắng của baseline English thành lựa chọn tốt cho phiếu Việt.
2. **Cải thiện association có kiểm soát.** Với mẫu đã kiểm chứng, dùng vùng
   label/result/reference rõ ràng và chuẩn hóa tọa độ. Với mẫu chưa biết, thử
   ràng buộc hàng/cột, đơn vị, tính duy nhất và khoảng cách theo cấu trúc trang;
   đánh giá trên dữ liệu phát triển riêng. Không chỉ nới ngưỡng khoảng cách:
   cách đó có thể lấy nhầm cột tham chiếu. Template hiện vẫn cần label anchor,
   nên chỉ thêm ROI không tự sửa được nhãn OCR sai.
3. **Bổ sung phiếu thật được phép dùng.** Gán nhãn giá trị, đơn vị, ngày, bbox
   kết quả và tham chiếu. Tách theo người/phiếu gốc, dành holdout cho mẫu máy
   hoặc bố cục chưa gặp; không để ảnh gốc và ảnh biến đổi rơi vào hai split.
   Khởi đầu 100–200 phiếu là đề xuất pilot, không phải đảm bảo đủ để phát hành.
4. **Đánh giá ở mức dùng được.** Đo sai/bỏ sót theo field, ngôn ngữ và layout;
   đo nhầm tham chiếu, sai đơn vị/ngày, độ trễ và thời gian người dùng sửa.
   Giữ ảnh bằng chứng, dữ liệu gốc và bước xác nhận riêng trước khi lưu kết quả.

Chưa có căn cứ cần huấn luyện OCR từ đầu. Ưu tiên kiểm chứng recognizer phù hợp
và association trước; chỉ cân nhắc fine-tuning hoặc model hiểu bố cục phức tạp
sau khi có phân tích lỗi trên phiếu thật. OCR trong app tiếp tục bị khóa theo
trạng thái hiện tại; báo cáo này không thay đổi cổng phát hành.

## Nguồn và khả năng tái kiểm tra

- [Báo cáo so sánh](../../experiments/inbody_ocr_comparison_v1/report.md)
- [Metrics theo field và nhóm](../../experiments/inbody_ocr_comparison_v1/metrics.json)
- [Notebook 17](../../notebooks/17_inbody_spatial_ocr_comparison.ipynb)
- [Thiết kế và cách chạy pipeline](ocr_v6_spatial_extraction.md)
- [Tài liệu PaddleOCR chính thức](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html):
  phân biệt recognizer English/Latin và các ngôn ngữ được hỗ trợ. Hỗ trợ công
  bố không thay thế benchmark phiếu InBody của dự án.
