# AI Personal Health Assistant

Phase 5 đã có **MVP Module 01 chạy cục bộ**: React Native/Expo cho người dùng,
Next.js cho quản trị và FastAPI cho nghiệp vụ. Đây chưa phải bản phát hành production.
[Phạm vi và kết quả kiểm tra](docs/phase-5/README.md).

## Các luồng đã triển khai

- Đăng ký người trưởng thành tự khai báo, đăng nhập/session có thời hạn và đăng xuất.
- Consent tách riêng xử lý sức khỏe, phiếu, ảnh, hỗ trợ quản trị và nghiên cứu.
- Hồ sơ/bối cảnh sức khỏe có version; số đo có thời điểm, thiết bị, nguồn, lịch sử sửa.
- Tiến trình ngày/tuần dùng engine Phase 4, không nội suy hay trộn các nguồn.
- Phiếu JPEG/PNG/PDF được mã hóa; chép thủ công → đối chiếu → chọn trường → xác nhận.
- Mục tiêu cân nặng do người dùng duyệt, kiểm tra bằng bộ quy tắc riêng và có lịch sử.
- Xuất dữ liệu, tải nguồn qua API, xóa phiếu kèm bản chép/số đo liên quan, xóa tài khoản.
- Web quản trị: số lượng tổng hợp, tài khoản, hồ sơ hỗ trợ khi có consent và thống kê route API.

**OCR tự động, CV và planner sinh bằng LLM vẫn khóa.** OCR chưa có benchmark phiếu thật;
CV chưa qua uncertainty/real-capture gates. AI service giữ ở scaffold, chưa có inference
production hoặc provider LLM. Các module theo dõi ăn/ngủ/vận động và hội thoại chưa triển khai.
Model CNN mặc định trong thư mục nghiên cứu được giữ nguyên.

## Backend cục bộ

Cần Python 3.11+. Từ thư mục monorepo:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e packages/health-core -e "apps/api[dev]"
cd apps/api
../../.venv/Scripts/python.exe -m alembic upgrade head
../../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Mặc định dùng SQLite `apps/api/health.db`. Key phát triển được tạo tại
`apps/api/private-storage/.development-key`; thư mục này được bỏ qua khi Git/Docker build.
Giữ key nếu cần giải mã dữ liệu đã lưu. Có thể cấu hình qua `apps/api/.env`, xem `.env.example`.

[Swagger](http://localhost:8000/docs), [readiness](http://localhost:8000/ready).
Trong workspace nghiên cứu hiện tại cũng có thể dùng Python tại `../.venv/Scripts/python.exe`
từ thư mục monorepo; không cài Paddle vào môi trường API.

## Web quản trị

Cần Node 24.3+ thuộc nhánh 24 hoặc 26+. Từ thư mục monorepo:

```powershell
npm ci
npm run dev:web
```

Mở [web quản trị](http://localhost:3000). API proxy chạy trên server Next.js, cấu hình
`API_INTERNAL_URL` trong `apps/web/.env.local`. Browser dùng cookie HttpOnly và CSRF;
không lưu bearer token trong localStorage.

Tạo quản trị viên trong terminal khác, **chạy tại `apps/api`** để dùng cùng cấu hình DB:

```powershell
../../.venv/Scripts/python.exe ../../scripts/create_admin.py --email your-admin@example.com
```

Lệnh yêu cầu nhập và xác nhận mật khẩu, không có tài khoản/mật khẩu quản trị mặc định.
Public registration chỉ tạo role `user`. Quản trị không mặc nhiên được đọc hồ sơ sức khỏe.

## React Native

```powershell
npm run dev:mobile
```

App dùng Expo SDK 58; dùng Expo Go/dev build tương thích. Token native lưu trong SecureStore;
bản web của app chỉ giữ phiên trong bộ nhớ. Android emulator mặc định gọi
`http://10.0.2.2:8000`, iOS simulator dùng `http://localhost:8000`.
Điện thoại thật cần `EXPO_PUBLIC_API_URL` trong `apps/mobile/.env` là IP LAN máy phát triển
và API lắng nghe trên địa chỉ LAN phù hợp. Bản phát hành thật cần HTTPS.

Luồng thử: đăng ký → Hồ sơ/cấp consent xử lý → lưu hồ sơ → ghi số đo → xem tiến trình.
Với phiếu: cấp thêm consent phiếu → Số đo/Phiếu InBody → tải nguồn → chép → đối chiếu → xác nhận.
Không có nhận dạng ảnh/phiếu tự động đang hoạt động.

## Kiểm tra

Tại `apps/api` dùng môi trường Python API:

```powershell
../../.venv/Scripts/python.exe -m pytest -q
../../.venv/Scripts/python.exe -m alembic check
```

Tại monorepo:

```powershell
npm run typecheck
npm run build:web
.venv/Scripts/python.exe scripts/export_openapi.py
.venv/Scripts/python.exe scripts/check_research_core.py
.venv/Scripts/python.exe scripts/smoke_module01.py --report docs/phase-5/http-smoke.json
```

Smoke test cuối cần API cục bộ đang chạy; chỉ tạo dữ liệu giả lập và xóa tài khoản/file trong `finally`.
Từ `apps/mobile`: `npx expo export --platform android --platform ios --output-dir dist/native`.
Bundle thành công không thay thế kiểm tra SecureStore, picker và preview trên thiết bị thật.

## Docker và lưu trữ

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose **development** gồm PostgreSQL 17, API chạy Alembic trước startup, web, AI scaffold
và retention worker mỗi giờ. Dữ liệu/file/key nằm trong named volumes; `docker compose down`
không xóa volume. Không dùng cấu hình development này cho dữ liệu người dùng thật.
Docker Desktop phải đang chạy. Chưa xác minh build/chạy Docker hoặc PostgreSQL trên máy hiện tại.

Ngoài Compose, từ `apps/api` chạy `python -m app.maintenance` để xem số phiếu hết hạn,
`python -m app.maintenance --apply` để thực hiện xóa. Cần tự cấu hình lịch vận hành.
Nguồn phiếu hết hạn bị chặn đọc/xác nhận; task xóa cả bản chép và số đo từ nguồn đó.
Mục tiêu riêng/nhật ký duyệt được giữ đến khi xóa tài khoản. Bản xuất đã tải về và bản sao lưu
ngoài hệ thống cần chính sách xóa riêng.

[Kiến trúc](docs/architecture/overview.md) · [DB](docs/database/module-01.md) ·
[Phân quyền/quyền riêng tư](docs/security/access-control.md) · [API](docs/api/module-01.md) ·
[Quy tắc mục tiêu](docs/ai-design/goal-screening.md) · [Phần còn lại](docs/roadmap/README.md).
