# SmartSpend Pro

Ứng dụng quản lý tài chính cá nhân và lập kế hoạch bằng AI, dùng trên Windows, trình duyệt và iPhone PWA.

- Theo dõi thu/chi, ngân sách, khoản định kỳ và mục tiêu tiết kiệm.
- Tạo thực đơn, danh sách đi chợ và kế hoạch đi chơi với Gemini.
- Lưu dữ liệu bằng SQLite cục bộ hoặc PostgreSQL; hỗ trợ tài khoản và sổ riêng.

## Chạy nhanh

Chạy tại thư mục gốc dự án:

```powershell
python -m pip install -r requirements/desktop.txt
python -m launchers.browser
```

Mở `http://127.0.0.1:8000`, vào **Cài đặt** để cấu hình Gemini và kết nối dữ liệu. Trên Windows, có thể nhấn đúp `run_app.bat` để mở ứng dụng desktop.

## Cấu trúc

| Thư mục | Nội dung |
| --- | --- |
| `backend/` | FastAPI, nghiệp vụ, AI và kết nối dữ liệu |
| `frontend/` | Giao diện web và PWA |
| `launchers/` | Khởi chạy desktop và trình duyệt |
| `scripts/` | Công cụ cloud, home server và preview |
| `config/`, `requirements/` | Cấu hình phát triển và thư viện |
| `tests/` | Kiểm thử tự động và dữ liệu mẫu |
| `docs/` | Hướng dẫn, bản đồ mã nguồn và báo cáo kỹ thuật |

## Tài liệu

- [Cài đặt Windows, cấu hình và đóng gói EXE](docs/guides/desktop.md)
- [Sử dụng các chức năng tài chính](docs/guides/finance-guide.md)
- [Dùng iPhone qua cloud](docs/guides/iphone-cloud.md)
- [Triển khai HP home server](docs/guides/hp-home-server.md)
- [Tài khoản, sổ riêng và nâng cấp dữ liệu](docs/guides/private-accounts.md)
- [Bản đồ mã nguồn và lệnh kiểm tra](docs/source-layout.md)

## Kiểm tra

Sau khi cài `requirements/dev.txt` và chạy `npm ci`:

```powershell
python -m unittest discover -s tests -v
npm run test:ui
```

Các bài tích hợp PostgreSQL cần database thử riêng; xem hướng dẫn [sổ riêng](docs/guides/private-accounts.md).
