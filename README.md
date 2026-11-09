# SmartSpend Pro — Quản lý Tài chính, Lên Thực đơn Đi chợ & Kế hoạch Đi chơi bằng AI

Ứng dụng có thêm sổ thu/chi hằng ngày, tổng quan tháng, ngân sách theo danh mục, khoản định kỳ, mục tiêu tiết kiệm và hàng chờ giao dịch ngoại tuyến. Xem [hướng dẫn chức năng và nâng cấp dữ liệu](docs/finance-guide.md).

Muốn dùng iPhone qua 4G/5G khi máy tính tắt: xem [cấu hình hosting và đăng nhập cloud](docs/iphone-cloud.md).

Ứng dụng quản lý chi tiêu cá nhân thông minh theo kiến trúc **3 tầng (3-Tier Architecture)**:
- **Frontend**: Web Dashboard hiện đại, tương thích cả **Desktop (`.exe`)** và **iPhone PWA** (thêm vào Màn hình chính dùng full-screen).
- **Backend**: Python **FastAPI** + **Google Gemini AI** tích hợp bảng neo giá thực tế Việt Nam (`VN_PRICE_ANCHOR`).
- **Database**: **Supabase PostgreSQL** qua **SQLAlchemy ORM**, hoặc `SQLite` cục bộ khi chưa cấu hình PostgreSQL. Nếu PostgreSQL lỗi, app giữ nguồn dữ liệu đã chọn và yêu cầu kết nối lại.

---

## Cấu trúc Thư mục Dự án

```text
SmartSpendAI/
├── backend/
│   ├── __init__.py
│   ├── database.py       # Kết nối thông minh Supabase PostgreSQL & Fallback SQLite + quản lý config.json
│   ├── models.py         # SQLAlchemy ORM: Bảng Plan (plans) & PlanItem (plan_items)
│   ├── ai_service.py     # Lõi Gemini AI + Fallback Model + Bảng neo giá thực tế VN (VN_PRICE_ANCHOR)
│   └── api_server.py     # FastAPI RESTful Server + Phục vụ tĩnh Frontend PWA
├── frontend/
│   ├── index.html        # Giao diện Dashboard & Modal Cài đặt / QR iPhone PWA
│   ├── style.css         # Giao diện Responsive (Desktop 2 cột & iPhone Mobile)
│   ├── app.js            # Logic kết nối REST API, tick giỏ đi chợ & sửa giá trực tiếp
│   ├── manifest.json     # Cấu hình Web App Manifest cho PWA
│   └── sw.js             # Service Worker hỗ trợ cài đặt PWA
├── main.py               # Điểm khởi chạy ứng dụng (tự động mở trình duyệt & hiển thị IP LAN)
├── requirements.txt      # Danh sách thư viện Python
├── run_app.bat           # File chạy nhanh ứng dụng trên Windows
└── build_exe.bat         # File đóng gói ứng dụng thành SmartSpendPro.exe độc lập
```

---

## Hướng dẫn Cài đặt & Sử dụng

### Bước 1: Cài đặt thư viện
Mở Terminal / PowerShell tại thư mục dự án và chạy:
```powershell
pip install -r requirements.txt
```

### Bước 2: Khởi động ứng dụng
Nhấn đúp vào **`run_app.bat`** hoặc chạy lệnh:
```powershell
python main.py
```
Trình duyệt sẽ tự động mở địa chỉ `http://127.0.0.1:8000`.

### Bước 3: Cấu hình Gemini API Key & Supabase PostgreSQL
1. Trên giao diện Web Dashboard, nhấn nút **⚙️ Cài đặt** ở góc trên bên phải.
2. **Google Gemini API Key**: Lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/app/apikey) và dán vào ô số 1.
3. **Supabase PostgreSQL URI**:
   - Đăng nhập [Supabase Dashboard](https://supabase.com/dashboard), tạo Project miễn phí.
   - Nhấn nút **Connect** (trên thanh công cụ) $\rightarrow$ sao chép chuỗi **URI** (dạng `postgresql://postgres.[ref]:[password]@aws-0-...pooler.supabase.com:6543/postgres`).
   - Dán vào ô số 2 và nhấn **💾 Lưu & Kết nối Database**.
   - Database PostgreSQL cần được chuẩn bị theo [hướng dẫn nâng cấp sổ riêng](docs/private-accounts.md) trước, kể cả khi kết nối từ desktop. App kiểm tra schema và quyền truy cập trước khi lưu cấu hình mới; nếu lỗi, cấu hình cũ được giữ nguyên.

### Bước 4: Cài đặt lên iPhone (PWA)
1. Đảm bảo iPhone và máy tính đang kết nối chung một mạng Wi-Fi.
2. Nhấn nút **📱 iPhone PWA** trên thanh công cụ của ứng dụng.
3. Dùng Camera của iPhone quét mã QR trên màn hình để mở trong **Safari**.
4. Nhấn nút **Chia sẻ (Share)** ở dưới đáy trình duyệt Safari $\rightarrow$ chọn **Thêm vào Màn hình chính (Add to Home Screen)**.
5. Mở biểu tượng **SmartSpend** trên màn hình iPhone khi đi chợ/siêu thị để vừa mua hàng vừa tick chọn và sửa giá thực tế — dữ liệu sẽ đồng bộ ngay lập tức với máy tính qua Supabase!

---

## Đóng gói thành File `.exe` trên Windows
Nhấn đúp vào file **`build_exe.bat`** (hoặc chạy `./build_exe.bat` trong Terminal). Sau khi hoàn tất, file thực thi độc lập sẽ nằm tại:
```text
dist\SmartSpendPro.exe
```

Cài các phiên bản đã cố định bằng `python -m pip install -r requirements.txt` trước khi build. Script dừng và báo thất bại nếu thiếu thư viện hoặc PyInstaller lỗi. Chạy tự động bằng `build_exe.bat --no-pause`.

Desktop kiểm tra HTTP `/healthz` trước khi mở cửa sổ. Lỗi khởi động được lưu tại `%LOCALAPPDATA%\SmartSpendPro\logs\desktop.log`. Có thể kiểm tra khởi động không mở cửa sổ bằng `SmartSpendPro.exe --check-startup` (mã thoát 0 khi thành công).

Tích hoàn thành hạng mục có giá sẽ tự ghi chi và cập nhật biểu đồ; xem [quy tắc kế hoạch và thanh toán](docs/finance-guide.md).

## Kiểm thử

`python -m pip install -r requirements-dev.txt`, sau đó chạy `python -m unittest discover -s tests -v` và các file `tests/test_*.cjs` bằng Node. GitHub Actions chạy cả PostgreSQL riêng để kiểm tra migration/RLS, các bài JavaScript và build Windows. Cấu hình PostgreSQL thử nghiệm cục bộ được mô tả trong [sổ riêng](docs/private-accounts.md).

AI giới hạn 10 yêu cầu mỗi phút cho mỗi tài khoản và 2 yêu cầu đồng thời trên một server. Mỗi model chờ tối đa 20 giây, chỉ đổi sang model dự phòng khi nhận lỗi 404; không đổi model khi hết quota hoặc lỗi xác thực. Khi đặt `GEMINI_MODEL`, app chỉ gọi model đã chọn.

