# Chạy trên Windows

Các lệnh dưới đây chạy tại thư mục gốc dự án.

## Cài đặt và khởi chạy

```powershell
python -m pip install -r requirements/desktop.txt
```

Nhấn đúp `run_app.bat` để mở cửa sổ desktop, hoặc chạy bằng trình duyệt:

```powershell
python -m launchers.browser
```

Trình duyệt mở tại `http://127.0.0.1:8000`.

## Cấu hình

Trong **Cài đặt** của ứng dụng:

1. Nhập Gemini API Key lấy từ [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Dùng SQLite cục bộ hoặc nhập URI PostgreSQL. Với Supabase, lấy URI tại **Connect** trong dashboard.
3. Chuẩn bị schema và quyền truy cập theo [hướng dẫn sổ riêng](private-accounts.md) trước khi kết nối PostgreSQL, kể cả trên desktop.

Ứng dụng kiểm tra kết nối trước khi lưu; nếu lỗi, cấu hình cũ được giữ nguyên. Khi PostgreSQL mất kết nối, ứng dụng yêu cầu kết nối lại và giữ nguồn dữ liệu đã chọn.

AI giới hạn 10 yêu cầu/phút/tài khoản, 2 yêu cầu đồng thời/server và deadline 90 giây mỗi lần gọi model. Model dự phòng chỉ dùng khi nhận lỗi 404. Khi đặt `GEMINI_MODEL`, ứng dụng chỉ gọi model đó.

## Dùng iPhone trong cùng Wi-Fi

1. Giữ máy tính chạy ứng dụng và kết nối iPhone cùng mạng.
2. Nhấn **iPhone PWA**, quét QR và mở bằng Safari.
3. Chọn **Chia sẻ → Thêm vào Màn hình chính**.

Muốn dùng qua 4G/5G khi máy tính tắt, xem [hướng dẫn cloud](iphone-cloud.md). Quy tắc ghi chi từ kế hoạch được mô tả trong [hướng dẫn tài chính](finance-guide.md).

## Đóng gói EXE

Sau khi cài thư viện desktop, nhấn đúp `build_exe.bat`. Kết quả ở `dist/SmartSpendPro.exe`. Script dừng nếu thiếu thư viện hoặc PyInstaller lỗi. Chạy tự động bằng:

```powershell
.\build_exe.bat --no-pause
```

Desktop kiểm tra HTTP `/healthz` trước khi mở cửa sổ. Nhật ký lỗi ở `%LOCALAPPDATA%\SmartSpendPro\logs\desktop.log`. Kiểm tra bản EXE mà không mở cửa sổ bằng `SmartSpendPro.exe --check-startup`; mã thoát `0` là thành công.
