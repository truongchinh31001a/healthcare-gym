# Truy cập và vòng đời dữ liệu

- Password dùng Argon2id; opaque token ngẫu nhiên chỉ lưu SHA-256 trong DB. Role đọc lại từ DB mỗi request.
- Session hết hạn sau 12 giờ mặc định, logout xóa session. Native token trong SecureStore; web cookie
  HttpOnly/SameSite=Strict, Secure ngoài development. Cookie write cần Origin trong allowlist và CSRF HMAC.
- Register không nhận role. Tạo admin bằng CLI nhập mật khẩu; không tự promote tài khoản đã tồn tại.
- Số đo/tài liệu/draft/mục tiêu chỉ qua `/me/*`. ID người khác trả 404; không tin user ID từ client.
- Admin đọc aggregate/tài khoản. Hồ sơ hỗ trợ cần `admin_support` đang bật; truy cập ghi trong audit của subject.
- Consent append-only theo mục đích/policy version. Research không được gộp với processing và hiện chưa kích hoạt training.
- Rút health processing chặn ghi mới và tính tiến trình, giữ quyền đọc/xuất/xóa. Rút document processing chặn
  chép/xác nhận mới; chủ sở hữu vẫn đọc/xóa dữ liệu hiện có. Consent hỗ trợ được kiểm tra lại mỗi request.
- Payload sức khỏe và audit values mã hóa authenticated bằng Fernet; file nguồn cũng mã hóa. Email, role,
  ownership/kind/IDs và thời gian định tuyến vẫn là metadata rõ trong DB; cần bảo vệ DB/backup bằng hạ tầng.
- Development key chỉ dùng cục bộ. Staging/production từ chối startup khi thiếu key, PostgreSQL hoặc HTTPS origins.
  Key cần quản lý ngoài DB/volume dữ liệu, có backup/rotation và phân quyền riêng trước phát hành thật.
- Upload raw streamed, tối đa 10 MiB; JSON tối đa 1 MiB; reject NaN/Infinity/overflow. File sniff JPEG/PNG/PDF,
  một frame ảnh/25 MP, PDF 1–5 trang. Dùng UUID server làm đường dẫn; không lưu tên file do client chỉ định.
  Không spool multipart plaintext. Nguồn trả attachment/no-store/nosniff qua authenticated endpoint.
- Nguồn phiếu mặc định hết hạn 30 ngày. Retention task xóa nguồn + drafts + derived observations và yêu cầu
  kiểm tra lại goal đang active. Mục tiêu/nhật ký duyệt độc lập vẫn giữ đến xóa tài khoản; backup/export bên ngoài
  không nằm trong khả năng xóa của MVP. Nguồn xác nhận chỉ một lần; muốn thay nguồn phải xóa rồi tải lại.
- Account delete cần mật khẩu và xóa records, consent, audit riêng tư, file và sessions. Không có recovery trong app.
- Login rate limit theo fingerprint HMAC của email/IP trong DB (10/50 attempts mỗi 15 phút); không tin X-Forwarded-For.
  Production cần proxy tin cậy + distributed rate limit/quota, secret management và review riêng.
- Request logs chỉ route template, status, duration và request ID; không log token/body. SQLAlchemy ẩn bind parameters.
  Metrics chỉ admin, tổng hợp trong một process; chưa có monitoring/alert/backup production bên ngoài.

MVP không thay thế kiểm thử xâm nhập, đánh giá tuân thủ hay thẩm định lâm sàng.
Tài liệu: [Argon2 parameters](https://argon2-cffi.readthedocs.io/en/stable/parameters.html),
[Fernet](https://cryptography.io/en/latest/fernet/).
