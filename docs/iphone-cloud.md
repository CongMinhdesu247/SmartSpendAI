# Dùng SmartSpend trên iPhone khi máy tính tắt

App cần backend chạy trên hosting và một địa chỉ HTTPS. Database đám mây không thay thế cho backend Python. Không dùng tunnel phụ thuộc máy tính cho yêu cầu này.

## Các phần đã chuẩn bị

- `Dockerfile`: Python server riêng, không cài giao diện desktop.
- `render.yaml`: Web Service Docker ở Singapore, gói Free, kiểm tra `/healthz`.
- Đăng nhập bằng tài khoản riêng và mật khẩu Argon2id; phiên đăng nhập lưu trong database, cookie HttpOnly/Secure/SameSite Strict trên cloud. Đăng xuất thu hồi phiên ở server. Xem [quy trình nâng cấp sổ riêng](private-accounts.md) trước khi phát hành phiên bản này.
- API dữ liệu yêu cầu đăng nhập. API không trả về khóa Gemini/chuỗi kết nối thô. Cấu hình cloud được quản lý bằng biến môi trường.
- Cloud yêu cầu PostgreSQL và không chuyển sang SQLite tạm khi lỗi kết nối.
- QR được tạo trong app, không gửi địa chỉ app sang dịch vụ QR bên ngoài.
- `configure_cloud.py` để desktop mở cùng app online với iPhone.

## Triển khai

Kết nối Render với phiên làm việc để trợ lý có thể tiếp tục tạo dịch vụ và kiểm tra URL. Chưa có dịch vụ hoặc URL online chỉ từ việc tạo các file cấu hình.

Nếu triển khai thủ công:

1. Đưa mã nguồn lên repository riêng và kết nối repository với Render. Có thể dùng nội dung của `output/deployment/SmartSpend-cloud-source.zip`; ZIP này không chứa database, cấu hình hoặc mật khẩu thật.
2. Tạo Blueprint từ `render.yaml`, hoặc Web Service dùng Dockerfile. Chọn Free nếu chỉ dùng cá nhân/thử nghiệm; không tự nâng lên gói trả phí.
3. Thêm biến môi trường từ file **`.env.cloud` trên máy của bạn** trong bảng điều khiển hosting. Không đưa file này lên repository và không dán nội dung vào chat.
4. Render tự cấp `RENDER_EXTERNAL_URL`. Với provider khác, đặt `SMARTSPEND_PUBLIC_URL` bằng địa chỉ HTTPS chính xác của app.
5. Chờ deployment thành công. `/healthz` phải trả `{"status":"ok"}`; API `/api/finance/categories` khi chưa đăng nhập phải trả `401`.
6. Mở URL bằng Safari trên iPhone. Mật khẩu nằm trong `output/deployment/login-private.txt` trên máy của bạn. Có thể lưu vào trình quản lý mật khẩu cá nhân.
7. Trong Safari, dùng Chia sẻ → Thêm vào Màn hình chính. Dùng cùng địa chỉ này qua Wi-Fi và 4G/5G. Nếu bản cài màn hình chính có phiên riêng, đăng nhập lại tại đó.

[Render hỗ trợ HTTPS và có các giới hạn cho Free Web Service](https://render.com/docs/free): app có thể ngủ sau 15 phút không dùng và cần khoảng một phút để khởi động lại. Dữ liệu không nằm trên filesystem tạm của Render; app dùng PostgreSQL đã cấu hình. Chưa triển khai đồng nghĩa chưa thể xác nhận việc mở từ mạng di động thật.

## Dùng cùng một app trên máy tính

Sau khi có URL thật, chạy:

```powershell
python configure_cloud.py
```

Dán URL HTTPS khi được hỏi, rồi mở lại `run_app.bat`. Desktop sẽ mở app online, không khởi chạy một backend local riêng. Mật khẩu đăng nhập giống trên iPhone. Chưa chạy bước này nếu chưa có URL triển khai thật.

## Dữ liệu và sao lưu

`migrate_cloud_data.py` mặc định chỉ kiểm tra. `--apply` sao lưu SQLite bằng snapshot nhất quán rồi sao chép sang database cloud **trống**. Giữ nguyên ID, checkbox và giao dịch liên kết; không xóa SQLite gốc. Dừng khi đích có dữ liệu khác, không tự trộn hoặc ghi đè. Báo cáo nằm ở `output/deployment/migration-report.json`.

Trong lần cấu hình này, kết nối PostgreSQL đã được kiểm tra và dữ liệu cũ đã được sao lưu/chuyển, đối chiếu số bản ghi. Bảng dữ liệu mới và bảng kế hoạch bật RLS; backend dùng vai trò chủ sở hữu qua kết nối trực tiếp.

Không đưa SQLite, bản sao lưu, `.env.cloud`, mật khẩu hoặc `config.json` lên repository/container. Mã hóa URL password được xử lý trước khi kết nối, và driver psycopg2 được chọn rõ ràng để tương thích với [thay đổi driver mặc định trong SQLAlchemy 2.1](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html).

## Kiểm tra trước khi bàn giao URL

- Kiểm thử API: `python -m unittest discover -s tests -v`.
- Kiểm tra browser bằng database tạm riêng: `python tests/serve_access_preview.py`. Mật khẩu trong script này chỉ là fixture thử nghiệm, không dùng cho hosting.
- Kiểm tra đăng nhập đúng/sai, API khi chưa đăng nhập, đăng xuất và QR trên kích thước iPhone.
- Kiểm tra URL triển khai thật và đăng nhập từ Safari/4G sau khi có hosting.

Phiên bản sổ riêng cần chạy migration trước khi deploy. Sau nâng cấp, mỗi người đăng ký tài khoản và chỉ truy cập sổ của mình; sổ cũ thuộc `chuso` với mật khẩu hiện tại. Database vẫn là Supabase hiện tại, không cần tạo thêm database. Chưa có chức năng chia sẻ sổ hoặc khôi phục mật khẩu qua email.
