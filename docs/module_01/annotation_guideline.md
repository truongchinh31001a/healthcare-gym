# InBody annotation guideline — v0.1

Phạm vi bản đầu: 9 trường trong `configs/inbody_fields.json`. Mọi giới hạn số học
chỉ để phát hiện lỗi chép dữ liệu, **không phải ngưỡng sức khỏe hay chẩn đoán**.

1. Chỉ nhận tài liệu có quyền sử dụng và consent phù hợp; tách consent xử lý cá nhân
   với sử dụng nghiên cứu/huấn luyện. Dùng ID ngẫu nhiên; bỏ tên, số điện thoại, ID
   bệnh nhân, QR/barcode và metadata định danh trước khi chia sẻ cho người gán nhãn.
2. Giữ ảnh gốc trong vùng riêng tư; mọi crop/biến thể phải trỏ về `original_document_id`.
   Không đưa tài liệu thật vào Git, notebook output, báo cáo công khai hay dịch vụ OCR ngoài.
   Môi trường local hiện tại chỉ là nghiên cứu, chưa có kiểm soát truy cập/mã hóa production.
3. Gán `subject_id`, `original_document_id`, thời điểm đo, thiết bị nếu đọc được;
   ghi `null` khi chưa biết. Ngày mơ hồ như 01/02/26 cần người kiểm tra, không đoán.
4. Với mỗi trường, lưu văn bản chép nguyên gốc, đơn vị in trên phiếu, bbox nhãn/giá trị
   theo tọa độ pixel của trang nguồn, số trang, giá trị chuẩn hóa và người kiểm tra.
   `bbox` theo `[x_min,y_min,x_max,y_max]`, gốc trên trái; đánh số trang từ 0.
5. Không lấy cột khoảng tham chiếu, lịch sử lần đo trước hoặc mục tiêu để điền kết quả hiện tại.
   Không thể đọc/không có trường: `null` cùng lý do, không dùng 0 thay missing.
6. Đơn vị chuẩn: kg, cm, L, %, ratio, kcal/day, kg/m2. Đổi lb × 0.45359237;
   in × 2.54. Dấu phẩy thập phân được hỗ trợ; dấu phân cách hàng nghìn hoặc cột nhiều
   giá trị cần kiểm tra thủ công. ECW/TBW là tỉ số, không tự đổi sang phần trăm.
7. Hai người đọc độc lập với tập kiểm thử thật, phân xử bất đồng và lưu lịch sử sửa.
   JSON mẫu annotation thật ở `schemas/inbody_annotation.example.json`.
8. Chia tập theo người và phiếu gốc: toàn bộ trang, crop, ảnh chụp lại và augmentation
   của cùng phiếu/người phải ở cùng một split. Cân nhắc holdout theo thiết bị/nguồn/layout.
   Chỉ dùng dev để sửa parser; không điều chỉnh theo lỗi test đã công bố.
9. Báo CER/WER khi có transcript; field exact match/F1; MAE riêng từng trường và đơn vị,
   coverage/missing, document success, correction rate từ phiên review thật và latency.
   Không gộp kg, %, L thành một MAE; không tính null/null là field true positive.

Parser hiện chỉ đọc các hàng nhãn–giá trị đơn giản. Trường visceral fat, segmental,
ngày đo nhiều định dạng và tên thiết bị sẽ được thêm sau khảo sát phiếu được cấp quyền.


Cập nhật spatial parser: [pipeline mới](ocr_v6_spatial_extraction.md) có `layout.json` lưu bbox/token IDs
và cần template được kiểm chứng khi bố cục mơ hồ. Bộ ghép chung vẫn giới hạn ở nhãn chuẩn và hàng rõ ràng;
không thay thế annotated real layouts hoặc quy trình đối chiếu. Fixture bbox mới dùng tọa độ trang đã EXIF-transpose,
được ghi rõ trong annotation; không trộn chúng với tọa độ ảnh raw chưa xoay.
