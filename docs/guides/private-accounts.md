# Tài khoản, Mã mời và Sổ riêng

Mỗi tài khoản sở hữu giao dịch, danh mục, ngân sách, khoản định kỳ, mục tiêu, sở thích và kế hoạch riêng biệt. Backend xác định người dùng từ phiên đăng nhập trên máy chủ, đồng thời PostgreSQL cưỡng chế cô lập dữ liệu bằng Row-Level Security (`smartspend_ledger`).

## Kiểm soát đăng ký tài khoản mới

Để bảo vệ cơ sở dữ liệu và hạn mức `GEMINI_API_KEY` của chủ ứng dụng, **chế độ đăng ký công khai mặc định được KHÓA** (`SMARTSPEND_ALLOW_REGISTRATION=0`).

Bạn có 3 chế độ vận hành trên Cloud / Home Server:

1. **Cá nhân (Mặc định — An toàn nhất):** Để `SMARTSPEND_ALLOW_REGISTRATION=0` và `SMARTSPEND_INVITE_CODE=` trống. Chỉ tài khoản chủ sổ (`chuso`) hoặc các tài khoản đã tạo trước đó đăng nhập được.
2. **Gia đình / Nhóm kín bằng Mã mời (Khuyên dùng khi chia sẻ):** Đặt `SMARTSPEND_INVITE_CODE=<ma-bi-mat-cua-gia-dinh>`. Giao diện đăng ký chỉ cho phép tạo sổ mới khi nhập đúng mã mời này.
3. **Mở đăng ký tự do (Chỉ dùng trong mạng nội bộ tin cậy):** Đặt `SMARTSPEND_ALLOW_REGISTRATION=1` và để trống `SMARTSPEND_INVITE_CODE`.

## Bảo mật phiên & Đổi mật khẩu

- Mật khẩu được băm bằng `Argon2id`.
- Người dùng đã đăng nhập có thể tự **Đổi mật khẩu** ngay trong tab **Tài khoản → Đổi mật khẩu truy cập** (tự động thu hồi toàn bộ phiên cũ trên các thiết bị khác) hoặc bấm **Đăng xuất khỏi mọi thiết bị**.
- Khi phiên hết hạn (`401`) hoặc đăng xuất, dữ liệu cache cục bộ trên trình duyệt tự động được dọn sạch.

## Quy trình nâng cấp schema PostgreSQL

1. Kiểm tra trước (chỉ đọc): `python -m scripts.cloud.migrate_ledgers`
2. Sao lưu và áp dụng nâng cấp: `python -m scripts.cloud.migrate_ledgers --apply`
3. Kiểm tra lại trạng thái role và RLS: `python scripts/homeserver/check_database.py`
