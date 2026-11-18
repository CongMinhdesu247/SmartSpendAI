# Chạy trên Windows Desktop

Các lệnh dưới đây chạy tại thư mục gốc dự án.

## Cài đặt và khởi chạy

```powershell
python -m pip install -r requirements/desktop.txt
```

Nhấn đúp `run_app.bat` để mở cửa sổ Desktop, hoặc mở trên trình duyệt:

```powershell
python -m launchers.browser
```

Ứng dụng mặc định chỉ lắng nghe an toàn tại `http://127.0.0.1:8000` (không mở cổng ra mạng Wi-Fi công cộng).

Nếu bạn đã cấu hình địa chỉ Cloud HTTPS nhưng muốn tạm mở lại bản cục bộ trên máy tính, chạy:

```powershell
python -m launchers.desktop --local
# Hoặc xóa địa chỉ Cloud đã lưu:
python -m launchers.desktop --reset-cloud
```

## Cấu hình AI & Nguồn dữ liệu

Mở tab **Tài khoản → Cài đặt AI & Nguồn dữ liệu**:

1. Nhập **Gemini API Key** lấy từ [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Chọn để trống ô PostgreSQL nếu muốn lưu bằng SQLite trên máy, hoặc nhập URI PostgreSQL (nhớ chạy bước nâng cấp [sổ riêng](private-accounts.md) trước khi nối PostgreSQL).
3. Tùy chọn bật **Cho phép điện thoại cùng mạng Wi-Fi truy cập trực tiếp** nếu muốn dùng trên iPhone trong mạng gia đình (cần khởi động lại ứng dụng sau khi lưu).

## Dùng trên iPhone trong cùng Wi-Fi

1. Bật quyền mạng Wi-Fi nội bộ trong **Cài đặt AI & Nguồn dữ liệu** và mở lại ứng dụng.
2. Vào **Tài khoản → Cài ứng dụng trên iPhone (PWA)**, quét mã QR bằng Camera iPhone.
3. Trong Safari, nhấn **Chia sẻ → Thêm vào Màn hình chính**.

Muốn dùng qua 4G/5G khi máy tính tắt, xem [hướng dẫn Cloud](iphone-cloud.md) hoặc [Home Server](hp-home-server.md).

## Đóng gói EXE

```powershell
.\build_exe.bat --no-pause
```

File thực thi nằm tại `dist\SmartSpendPro.exe`. Khi cài đặt vào thư mục không có quyền ghi (như `C:\Program Files`), ứng dụng tự động lưu dữ liệu và hồ sơ trình duyệt vào `%LOCALAPPDATA%\SmartSpendPro`. Nhật ký khởi động nằm tại `%LOCALAPPDATA%\SmartSpendPro\logs\desktop.log`.
