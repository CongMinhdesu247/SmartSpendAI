# Kết quả kiểm tra bộ triển khai HP — 17/11/2026

Đã chạy trên Docker Desktop của PC với container Linux amd64, không phải HP. Không SSH, thay DNS, cài cron hoặc thay đổi website/server thật.

## Đã xác minh

- Build `Dockerfile.hp` với Python 3.13 và toàn bộ phiên bản thư viện trong `requirements/homeserver.lock.txt` thành công. Image nền Python/Postgres khóa digest.
- Compose riêng `smartspend-hp-test`: PostgreSQL 18 khởi tạo volume mới, tạo các role cần thiết; migration trên database trống thành công và chạy lại trả `already_applied`.
- Web và DB healthy. Chỉ web publish `127.0.0.1:18092`; DB không publish port ra host. HTTP `/healthz` trả 200.
- `tests/hp_container_smoke.py`: trang chủ tải được; Host sai trả 400; khách chưa đăng nhập gọi API riêng trả 401; đăng nhập `chuso` thành công; cookie có Secure; hai tài khoản mới có sổ riêng; tài khoản khác không đọc/xóa được giao dịch (404).
- `check_database.py`: app DB login không có SUPERUSER, BYPASSRLS, CREATEDB, CREATEROLE; truy cập qua ledger role thành công.
- Chạy thật `backup.sh` trong môi trường Linux dùng Docker CLI: tạo custom dump, kiểm tra danh mục dump, chép cấu hình, tạo COMPLETE và gói export thành công.
- Phục hồi dump giữ ACL bằng `pg_restore --role=smartspend --no-owner --exit-on-error` vào project riêng `smartspend-hp-restore-test`. Mã thoát 0; kiểm tra schema/role và số bản ghi sau restore: 3 tài khoản, 27 danh mục, 3 preferences, 1 giao dịch, trùng dữ liệu fixture đã tạo.
- Bộ kiểm thử Python hiện có: 56 tests, OK, 12 bài tích hợp PostgreSQL được skip vì không đặt `SMARTSPEND_TEST_POSTGRES_URL`. Các bài này không được tính là đã chạy; kiểm tra PostgreSQL container ở trên là lượt độc lập.
- Bài kiểm thử mới `test_hp_setup.py`: 1 test OK; mật khẩu được băm đúng, hash `$argon2id$` giữ nháy đơn cho Compose và cấu hình đã có không bị tự sinh lại secret DB.
- 5 nhóm kiểm thử JavaScript của `npm run test:ui` đều thành công.
- Kiểm tra cú pháp Bash và định dạng Python của các file thay đổi thành công. Tag chính thức `cloudflare/cloudflared:2026.10.0` có manifest tải được; chưa chạy tunnel public.

Một ảnh chụp tài nguyên lúc gần nhàn rỗi trên PC: web khoảng 77 MiB, DB khoảng 36 MiB. Đây không phải kiểm thử tải hoặc ước lượng mức đỉnh trên HP; giới hạn cấu hình cao hơn để dành chỗ cho AI, kết nối và băm mật khẩu.

## Lỗi đã sửa khi xác minh

Migration cũ gọi `Base.metadata.create_all` trước khi đảm bảo nạp model. Khi chạy từ tiến trình migration mới trên database trống, có thể gặp `NoSuchTableError`. Đã chuyển bước nạp danh sách ledger/model lên trước `create_all`; chạy lại trên database trống thành công.

## Chưa xác minh

- Cổng 8092 trên HP, tên/cổng web thứ hai, RAM/CPU/đĩa còn lại khi cả ba web chạy.
- SSH key/Tailscale trên PC hiện tại, domain thực sự sở hữu, cấu hình connector/tunnel thật.
- HTTPS/đăng nhập/PWA qua 4G, Gemini API với key thật và quota/model đang dùng.
- Tải đồng thời, migration dữ liệu thật từ SQLite/Supabase, phục hồi toàn bộ app trên HP sau hỏng máy.
- Lịch backup, tải backup tự động về PC, tích hợp monitor Telegram và tự phục hồi sau reboot trên HP.

Các container thử trên PC được dừng sau kiểm tra; volume fixture giữ lại để đối chiếu. Các file và dữ liệu thử nằm trong `output/hp-test/`, không nằm trong gói bàn giao.
