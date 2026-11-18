# SmartSpend Pro

Ứng dụng quản lý tài chính cá nhân, chấm điểm sức khỏe dòng tiền, cố vấn AI và lập kế hoạch thông minh — hoạt động mượt mà trên Windows Desktop, trình duyệt Web, Local Server Docker và iPhone PWA (hỗ trợ chế độ Sáng/Tối & Ngoại tuyến).

- **Sổ chi tiêu & Nhập nhanh tiếng Việt + Bảng Lệnh `Ctrl+K`:** Gõ tự nhiên `35k5 phở bò`, `50 cành bún chả`, `2 lít đổ xăng`, `1tr5 tiền nhà`, `+15tr lương`, `45k cà phê 15/11`, hoặc nhấn `Ctrl+K` mở **Command Palette** điều hướng và ghi chi tức thì.
- **Điểm Sức Khỏe Tài Chính 4 Trụ Cột & Xu Hướng 6 Tháng:** Vòng tròn điểm 0–100 minh bạch 4 trụ cột, **Dự báo tổng chi cuối tháng**, biểu đồ kép (**Nhịp lũy kế tháng** ↔ **Xu hướng Thu-Chi 6 tháng**), **Lịch nhiệt độ chi tiêu** chạm ngày để lọc, biểu đồ Doughnut danh mục, sao chép hạn mức tháng trước 1 chạm và nhắc hóa đơn định kỳ.
- **Cố vấn Tài chính AI có Trọng tâm & Kế hoạch Thông minh:** Tích hợp **Gemini AI** vừa phân tích dòng tiền thực tế theo mục tiêu (*Giảm ăn ngoài*, *Tiết kiệm 20%*, *Phanh mua sắm*), vừa thiết kế thực đơn đi chợ gộp / lịch trình đi chơi sát giá Việt Nam; hỗ trợ chế độ đi chợ tập trung (ẩn mục đã mua), nhân bản giao dịch và chép danh sách gửi Zalo/Ghi chú.
- **Bảo mật chiều sâu & Cập nhật Local Server 0% mất dữ liệu:** Cô lập sổ bằng PostgreSQL Row-Level Security (`smartspend_ledger`), băm `Argon2id` chống dò thời gian, chặn tràn bộ nhớ `chunked` stream (`413`), chống giả mạo IP sau Proxy, `CSP script-src 'self'`, Sao lưu JSON v2 trọn vẹn và trình cập nhật 1 lệnh `deploy_update.ps1`.

## Chạy nhanh trên máy tính

```powershell
python -m pip install -r requirements/desktop.txt
python -m launchers.browser
```

Mở `http://127.0.0.1:8000`, vào **Tài khoản → Cài đặt AI & Nguồn dữ liệu** để nhập Gemini API Key hoặc cấu hình PostgreSQL. Trên Windows, nhấn đúp `run_app.bat` để mở cửa sổ Desktop. Nhấn phím `?` bất kỳ lúc nào trên giao diện để xem bảng phím tắt (`N`, `Q`, `/`, `1-3`, `D`).

## Cập nhật nhanh lên Local Server (Docker Compose)

Dự án đi kèm cấu hình chuẩn theo [SERVER_CONTEXT.md](SERVER_CONTEXT.md) (`source/`, `data/`, `.env`, `docker-compose.yml` và cấu hình mẫu `_proxy/sites/`):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "<ssh-alias>" -RemoteAppDir "~/apps/SmartSpendAI"
```

## Cấu trúc mã nguồn

| Thư mục | Nội dung |
| --- | --- |
| `backend/` | FastAPI app, `routers/{auth,finance,plans,system}.py`, `schemas/`, `access.py`, `ai_service.py`, `database.py`, `tenancy.py` |
| `frontend/` | Giao diện Web/PWA (`index.html`, `style.css`, `auth.js`, `app.js`, `finance.js`, `sw.js`, `icons.svg`) |
| `deploy/local-server/` | `docker-compose.yml` chuẩn `SERVER_CONTEXT.md` (mount `./data/`) & cấu hình Reverse Proxy (`sites/`) |
| `scripts/` | Công cụ cập nhật Local Server (`homeserver/update.sh`, `deploy_update.ps1`, `backup.sh`), Cloud & Preview |
| `launchers/` | Khởi chạy cửa sổ Desktop (`desktop.py`) và Trình duyệt (`browser.py`) |
| `config/`, `requirements/` | Cấu hình Tailwind/Prettier và danh sách thư viện theo môi trường |
| `tests/` | Bộ kiểm thử tự động Python & JavaScript |
| `docs/` | Hướng dẫn sử dụng, triển khai và báo cáo kiểm toán kỹ thuật |

## Tài liệu chi tiết

- [Báo cáo Kiểm toán Dự án & Các hạng mục Đã nâng cấp](docs/reports/project-audit-and-improvements.md)
- [Hồ sơ & Cấu hình Local Server (`SERVER_CONTEXT.md`)](SERVER_CONTEXT.md)
- [Triển khai & Cập nhật Local / Home Server với Docker Compose](docs/guides/hp-home-server.md)
- [Hướng dẫn sử dụng Sổ chi tiêu, Lịch nhiệt độ, AI Coach & Kế hoạch](docs/guides/finance-guide.md)
- [Cài đặt Windows, cấu hình và đóng gói EXE](docs/guides/desktop.md)
- [Dùng trên iPhone qua Cloud HTTPS](docs/guides/iphone-cloud.md)
- [Tài khoản, sổ riêng, mã mời và nâng cấp dữ liệu](docs/guides/private-accounts.md)
- [Bản đồ mã nguồn và lệnh phát triển](docs/source-layout.md)

## Kiểm tra tự động

Sau khi cài `requirements/dev.txt` và chạy `npm ci`:

```powershell
python -m unittest discover -s tests -v
npm run test:ui
```
