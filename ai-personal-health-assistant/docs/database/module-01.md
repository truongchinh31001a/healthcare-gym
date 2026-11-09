# Database v1

Alembic revision `076fcc3260f2` tạo `users`, `credential_sessions`, `login_attempts`, `consents`,
`records`, `audit_events`. PostgreSQL cho triển khai; SQLite cho local tests/development có foreign keys bật.

Records định tuyến theo owner/kind/slot, lưu JSON mã hóa cho profile, health_context, measurement_session,
observation, document, report_draft và goal. Singleton unique `(user_id, kind, slot)`; revisions bất biến
của observations là record mới, có supersedes link bên trong encrypted payload. Profile/context/goal dùng
version compare-and-swap và audit before/after. Nguồn report có atomic version lock để tránh xác nhận hai draft.

`parent_id` và `document_id` FK cascade xóa bản chép/số đo khi xóa nguồn; user FK cascade xóa toàn bộ private records.
File vật lý phải xóa cùng lifecycle ở application/maintenance. Xóa file trước commit ưu tiên loại bỏ nguồn;
nếu DB thất bại, API có thể tạm còn metadata trỏ tới file thiếu và trả 410; task có thể chạy lại.

Engine Phase 4 nhận payload đúng contract, quy đổi unit khi phân tích và giữ nguyên input. Thời điểm đo
có offset, date-only trên phiếu giữ đúng precision/timezone, thiếu ngày luôn null. Recorded/audit timestamp
server dùng logical tie breaker microsecond để thứ tự sửa không phụ thuộc độ phân giải clock Windows.
Snapshot hiện tại bao gồm mọi ingestion đã commit. Chưa có API as-of lịch sử ngoài engine nghiên cứu.

Không đọc riêng field sức khỏe bằng SQL vì payload mã hóa; MVP giải mã trong bộ nhớ sau kiểm tra ownership/consent.
Progress giới hạn 10.000 observation/account và yêu cầu export/offline khi vượt giới hạn, không cắt lịch sử âm thầm.
Chưa có kiểm chứng migration/runtime PostgreSQL vì Docker daemon của máy đang tắt.
