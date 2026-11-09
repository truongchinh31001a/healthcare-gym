# Sau MVP Phase 5

Đã có local integration cho auth, consent, hồ sơ, phiên đo, review phiếu, tiến trình, goal rules và admin.
Các điều kiện phát hành còn lại:

1. Benchmark phiếu InBody thật có consent và nhãn; chỉ sau release review mới tích hợp/mở OCR inference.
2. Prospective/external capture, RGB preprocessing và uncertainty/OOD gates cho CV; không đổi default CNN.
3. Kiểm chứng native trên Android/iOS thật: SecureStore, file picker/preview, lỗi mạng và export.
4. Chạy build/integration PostgreSQL/Docker và concurrent requests; thêm quotas/rate limit production,
   secret/key rotation, encrypted backups/deletion/retention, monitoring/alerts và review bảo mật.
5. Clinical/safety evaluation và yêu cầu pháp lý trước khi dùng dữ liệu thật hoặc triển khai planner LLM.
6. Module ăn/ngủ/vận động, trợ lý hội thoại và các loại goal ngoài cân nặng nằm ở các bước sau.

`deploy.yml` vẫn là placeholder; chưa có release, cloud upload hoặc deployment thật.
