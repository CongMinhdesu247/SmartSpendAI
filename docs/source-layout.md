# Bản đồ mã nguồn

## Cây thư mục dự án

```text
SmartSpendAI/
├── backend/                  # API, nghiệp vụ, bảo mật và kết nối dữ liệu
│   ├── routers/              # Tách bạch toàn bộ HTTP routers theo miền nghiệp vụ
│   │   ├── auth.py           # Đăng nhập, đăng ký mã mời, đổi mật khẩu, giới hạn phiên
│   │   ├── finance.py        # Sổ thu/chi, Xu hướng 6 tháng, AI Coach, Định kỳ, Mục tiêu, Sao lưu v2
│   │   ├── plans.py          # Kế hoạch AI & Thủ công, đồng bộ checklist hai chiều, Thùng rác
│   │   └── system.py         # Cấu hình hệ thống, LAN IP, mã QR, /healthz kiểm tra kết nối DB
│   ├── services/             # Tầng dịch vụ nghiệp vụ thuần khiết (tách khỏi HTTP router)
│   │   ├── insights.py       # Chấm điểm sức khỏe 4 trụ cột, dự báo cuối tháng, xu hướng 6 tháng
│   │   └── backup.py         # Xuất & Khôi phục toàn diện JSON v2 chống trùng lặp
│   ├── schemas/              # Validation Pydantic nghiêm ngặt (access, ai, finance, plans)
│   ├── access.py             # Middleware bảo mật, Rate Limiter nhận diện Proxy, CSRF/Host/Body & CSP
│   ├── auth_models.py        # Model tài khoản & phiên đăng nhập
│   ├── finance_models.py     # Model sổ tài chính & lưu trữ
│   ├── models.py             # Model kế hoạch & hạng mục
│   ├── tenancy.py            # Cô lập sổ riêng ở cả tầng ORM và PostgreSQL RLS
│   ├── ai_service.py         # Gemini AI lập kế hoạch & Cố vấn tài chính tháng
│   └── database.py           # Quản lý kết nối PostgreSQL / SQLite & load_all_models()
├── frontend/                 # HTML, CSS, JavaScript (CSP-strict, không inline handler) & PWA
│   ├── icons/                # Biểu tượng PWA
│   └── vendor/               # Chart.js tự lưu trữ cục bộ
├── deploy/                   # Cấu hình hạ tầng triển khai chuẩn hóa
│   └── local-server/         # Chuẩn SERVER_CONTEXT.md: docker-compose.yml (./data/) & sites/ Proxy
├── scripts/                  # Công cụ vận hành tự động
│   ├── cloud/                # Chuẩn bị gói nguồn, cấu hình và chuyển dữ liệu Cloud
│   ├── homeserver/           # update.sh, deploy_update.ps1, backup.sh, configure.py, migrate.py
│   └── previews/             # Server giao diện với dữ liệu mẫu cô lập
├── launchers/                # Điểm khởi chạy ứng dụng (desktop.py, browser.py)
├── requirements/             # Danh sách thư viện theo môi trường (server, desktop, dev, lock)
├── config/                   # Cấu hình Tailwind CSS & Prettier
├── tests/                    # Kiểm thử tự động Python & Node.js
├── docs/                     # Hướng dẫn sử dụng, triển khai và báo cáo kiểm toán kỹ thuật
└── SERVER_CONTEXT.md         # Hồ sơ cấu trúc Local Server & hướng dẫn cập nhật nhanh
```

## Tìm nơi chỉnh sửa nhanh

| Chức năng | File chính |
| --- | --- |
| Đăng nhập, đăng ký mã mời, đổi mật khẩu, bảo vệ CSRF/Host/HSTS | `backend/access.py`, `backend/routers/auth.py`, `frontend/auth.js` |
| Sổ thu/chi, Điểm sức khỏe, Lịch nhiệt độ, AI Coach, Sao lưu JSON v2 | `backend/routers/finance.py`, `frontend/finance.js` |
| Kế hoạch AI & Thủ công, Chế độ đi chợ, Chép văn bản gửi Zalo | `backend/routers/plans.py`, `backend/ai_service.py`, `frontend/app.js` |
| Cấu hình hệ thống, LAN IP, mã QR, `/healthz` kiểm tra DB | `backend/routers/system.py` |
| Triển khai & Cập nhật Local Server không mất dữ liệu | `deploy/local-server/`, `scripts/homeserver/update.sh`, `SERVER_CONTEXT.md` |

## Lệnh phát triển & kiểm tra

```powershell
python -m pip install -r requirements/dev.txt
npm ci
npm run build:css
python -m black .
npm run format
python -m black --check .
npm run format:check
python -m unittest discover -s tests -v
npm run test:ui
```

> **Lưu ý về CSP:** Dự án áp dụng `Content-Security-Policy: script-src 'self'; object-src 'none'` nghiêm ngặt (không dùng `'unsafe-inline'`). Mọi tương tác giao diện đều gắn qua `data-action` / `data-f-action` và `addEventListener`, tuyệt đối không viết inline `onclick` hay `onsubmit` trong HTML/JS.
