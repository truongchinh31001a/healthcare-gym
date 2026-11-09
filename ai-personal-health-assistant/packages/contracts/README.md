# Shared contracts

`src/index.ts` là các DTO TypeScript dùng chung cho Module 01 (duy trì thủ công).
`openapi.json` xuất từ FastAPI bằng `python scripts/export_openapi.py` trong monorepo.
Schemas request và progress/planner context đã có; response generic khác chưa sinh client tự động.
API tests xác minh các response progress/planner bằng JSON Schema của core; TypeScript kiểm tra cả web và mobile.
