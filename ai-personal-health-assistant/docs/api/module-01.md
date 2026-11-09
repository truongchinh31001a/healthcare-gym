# Module 01 API

Prefix `/api/v1`. [OpenAPI](../../packages/contracts/openapi.json) chứa schema request và progress/context;
[TS contracts](../../packages/contracts/src/index.ts) được duy trì thủ công và typecheck cùng clients.
Hai schema progress/context được kiểm tra với response trong API tests. Các response generic chưa có client sinh tự động.

| Endpoint | Chức năng |
|---|---|
| `POST /auth/register`, `/auth/login`, `/auth/logout`; `GET /auth/session` | Tài khoản/session |
| `GET/POST /me/consents` | Lựa chọn consent theo policy version |
| `GET/PUT /me/profile`, `/me/health-context` | Hồ sơ/bối cảnh có version |
| `POST /me/measurement-sessions` | Phiên đo, nhiều fields cùng phương pháp |
| `GET /me/observations`; `POST /me/observations/{id}/revisions` | Lịch sử/phân trang/điều chỉnh |
| `GET /me/progress`, `/me/planner-context?stream_id=...` | Dashboard và facts có gates |
| `POST/GET /me/documents`; `GET /me/documents/{id}/content`; `DELETE /me/documents/{id}` | Nguồn mã hóa; POST body là bytes raw |
| `POST /me/documents/{id}/transcription` | Tạo pending draft thủ công |
| `GET /me/report-drafts`, `/me/report-drafts/{id}`; `POST /me/report-drafts/{id}/confirm` | Đối chiếu, chọn fields/flags, xác nhận |
| `POST /me/documents/{id}/ocr` | Trả 409 vì release gate chưa đạt |
| `GET/POST /me/goals`; `PUT /me/goals/{id}`; `GET /me/goals/{id}/history` | Mục tiêu, user approval và audit |
| `GET /me/export`; `DELETE /me/account` | Xuất JSON/tải file riêng; xóa cần mật khẩu |
| `GET /capabilities` | Trạng thái gates đang khóa |
| `GET /admin/overview`, `/admin/users`, `/admin/metrics` | Tổng hợp/tài khoản/metrics |
| `GET /admin/users/{id}/support-profile` | Profile chỉ đọc khi có consent |

Các writes cookie cần Origin allowlisted + `X-CSRF-Token` từ login/session. Native bearer bỏ qua cookie/CSRF.
204 không có body. 401 hết phiên, 403 thiếu quyền/consent, 404 không thấy record đúng owner,
409 version/gate/conflict, 410 nguồn hết hạn/mất, 422 input, 429 rate limit.
`/health` là liveness; `/ready` kiểm tra bảng DB và cấu hình key. Không trả chi tiết lỗi DB ra ngoài.

Date/time, units, method, source và provenance do server kiểm tra/tạo. Client không thể gửi verified/inferred,
subject, reviewer hay consent ID để chiếm quyền. Corrections không sửa bản gốc; report review vẫn giữ extracted.
