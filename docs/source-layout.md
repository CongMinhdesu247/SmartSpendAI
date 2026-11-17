# Bản đồ mã nguồn

## Cây thư mục để làm việc

```text
SmartSpendAI/
├── backend/          # API, nghiệp vụ và database
│   └── schemas/      # Validation: kế hoạch, tài chính, AI, tài khoản
├── frontend/         # HTML, CSS, JavaScript và PWA
│   ├── icons/        # Biểu tượng ứng dụng
│   └── vendor/       # Thư viện bên ngoài và giấy phép
├── launchers/        # Các điểm khởi chạy
│   ├── desktop.py    # Cửa sổ desktop / đầu vào đóng gói EXE
│   └── browser.py    # Chạy bằng trình duyệt
├── scripts/          # Công cụ hỗ trợ
│   ├── cloud/        # Cấu hình, đóng gói và chuyển dữ liệu cloud
│   ├── homeserver/   # Cấu hình, đóng gói, migration và backup HP
│   └── previews/     # Server giao diện với dữ liệu thử riêng
├── requirements/     # Danh sách thư viện theo môi trường
│   ├── desktop.txt
│   ├── server.txt
│   ├── homeserver.lock.txt
│   └── dev.txt
├── config/           # Cấu hình công cụ phát triển
│   ├── tailwind.cjs
│   ├── prettier.json
│   └── prettier.ignore
├── tests/            # Kiểm thử tự động, smoke test và fixture
├── docs/
│   ├── guides/       # Cài đặt, sử dụng và triển khai
│   ├── reports/      # Kết quả xác minh và lịch sử sửa lỗi
│   └── source-layout.md  # Bản đồ mã nguồn và lệnh phát triển
├── .github/          # CI
├── .vscode/          # Cách hiển thị cây thư mục trong IDE
├── run_app.bat       # Bấm để chạy ứng dụng
└── build_exe.bat     # Bấm để đóng gói EXE
```

## Tìm nơi sửa chức năng

| Công việc | File chính |
| --- | --- |
| API kế hoạch, sao chép, khôi phục | `backend/api_server.py` |
| Validation của dữ liệu | `backend/schemas/` |
| Tích hoàn thành và tự ghi chi | `backend/plan_payments.py`, `frontend/app.js` |
| Giao dịch và báo cáo tháng | `backend/finance_api.py`, `frontend/finance.js` |
| Prompt và gọi AI | `backend/ai_service.py` |
| Giao diện | `frontend/index.html`, `frontend/style.css` |
| Đăng nhập và sổ riêng | `backend/access.py`, `backend/tenancy.py`, `frontend/auth.js` |
| Kết nối và cấu hình dữ liệu | `backend/database.py` |
| Cache PWA | `frontend/sw.js` |

Frontend tải `auth.js`, `app.js`, rồi `finance.js`. Các schema được nhập lại qua module API cũ để các import hiện có vẫn hoạt động.

## Chạy và kiểm tra

Chạy desktop bằng `run_app.bat`, đóng gói bằng `build_exe.bat`. Các lệnh Python chạy từ thư mục gốc:

```powershell
python -m pip install -r requirements/desktop.txt
python -m launchers.desktop
python -m launchers.browser
```

Công cụ cloud:

```powershell
python -m scripts.cloud.configure
python -m scripts.cloud.prepare
python -m scripts.cloud.migrate_data
python -m scripts.cloud.migrate_ledgers
```

Các lệnh migration mặc định kiểm tra trước; đọc [hướng dẫn cloud](guides/iphone-cloud.md) và [sổ riêng](guides/private-accounts.md) trước khi dùng `--apply`.

Phát triển và kiểm thử:

```powershell
python -m pip install -r requirements/dev.txt
npm ci
python -m black .
npm run format
python -m black --check .
npm run format:check
python -m unittest discover -s tests -v
npm run test:ui
```

`npm run build:css` tạo lại `frontend/tailwind.css` bằng cấu hình trong `config/tailwind.cjs`. Black đọc `pyproject.toml`; Prettier đọc các file trong `config/` thông qua lệnh npm.

Preview giao diện dùng dữ liệu thử riêng, chạy từ thư mục gốc:

```powershell
python scripts/previews/serve_preview.py
python scripts/previews/serve_access_preview.py
python scripts/previews/serve_accounts_preview.py
python scripts/previews/serve_cashflow_preview.py
python scripts/previews/serve_plan_sync_preview.py
```

Chỉ chạy một preview tại một thời điểm nếu trùng cổng. Hướng dẫn triển khai nằm trong `docs/guides/`; báo cáo cũ nằm trong `docs/reports/`. Dockerfile, Compose và Render giữ tại thư mục gốc để các lệnh triển khai hiện có tiếp tục hoạt động.

## Những file được ẩn trong Explorer

`.vscode/settings.json` ẩn `node_modules/`, `build/`, `dist/`, `output/`, `.playwright-cli/`, `__pycache__/`, các file `.spec`, cấu hình riêng và database cục bộ. Chúng vẫn nằm trên đĩa và ứng dụng vẫn sử dụng cùng đường dẫn. File chạy sau build nằm tại `dist/SmartSpendPro.exe`.

`package-lock.json` được xếp dưới `package.json`; cấu hình hosting được xếp dưới `Dockerfile`. Có thể đổi cách hiển thị trong `.vscode/settings.json`.

Database `smartspend_local.db`, bản sao lưu, `config.json` và `.env.cloud` giữ nguyên vị trí để bảo toàn dữ liệu hiện tại. Hướng dẫn nghiệp vụ nằm trong [sổ thu/chi](guides/finance-guide.md).
