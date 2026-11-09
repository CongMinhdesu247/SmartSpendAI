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
├── scripts/cloud/    # Công cụ quản trị cloud
│   ├── configure.py  # Cấu hình desktop mở app HTTPS
│   ├── prepare.py    # Tạo gói source và cấu hình cloud
│   ├── migrate_data.py     # Chuyển dữ liệu SQLite sang cloud
│   └── migrate_ledgers.py  # Nâng cấp PostgreSQL cho sổ riêng
├── requirements/     # Danh sách thư viện theo môi trường
│   ├── desktop.txt
│   ├── server.txt
│   └── dev.txt
├── config/           # Cấu hình công cụ phát triển
│   ├── tailwind.cjs
│   ├── prettier.json
│   └── prettier.ignore
├── tests/            # Kiểm thử, fixture và server preview
├── docs/             # Hướng dẫn
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

Các lệnh migration mặc định kiểm tra trước; đọc [hướng dẫn cloud](iphone-cloud.md) và [sổ riêng](private-accounts.md) trước khi dùng `--apply`.

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

## Những file được ẩn trong Explorer

`.vscode/settings.json` ẩn `node_modules/`, `build/`, `dist/`, `output/`, `.playwright-cli/`, `__pycache__/`, các file `.spec`, cấu hình riêng và database cục bộ. Chúng vẫn nằm trên đĩa và ứng dụng vẫn sử dụng cùng đường dẫn. File chạy sau build nằm tại `dist/SmartSpendPro.exe`.

`package-lock.json` được xếp dưới `package.json`; cấu hình hosting được xếp dưới `Dockerfile`. Có thể đổi cách hiển thị trong `.vscode/settings.json`.

Database `smartspend_local.db`, bản sao lưu, `config.json` và `.env.cloud` giữ nguyên vị trí để bảo toàn dữ liệu hiện tại. Hướng dẫn nghiệp vụ nằm trong [sổ thu/chi](finance-guide.md).
