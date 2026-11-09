# Tài khoản và sổ riêng

Mỗi tài khoản có giao dịch, danh mục, ngân sách, khoản định kỳ, mục tiêu, sở thích và kế hoạch AI riêng. Backend xác định người dùng từ phiên đăng nhập trên server, không nhận chủ sở hữu sổ từ nội dung biểu mẫu. PostgreSQL dùng vai trò `smartspend_ledger` không có quyền bỏ qua RLS để đọc/ghi sổ. Các bảng tài khoản và phiên không được cấp cho vai trò này hoặc Supabase Data API.

Đây là tài khoản của SmartSpend lưu trong PostgreSQL Supabase hiện tại; chưa tích hợp Supabase Auth, gửi email, quên mật khẩu hay chia sẻ sổ. Người dùng đăng ký bằng tên 3–32 chữ cái không dấu, số hoặc `_` và mật khẩu 12–128 ký tự. Ai có URL cũng có thể đăng ký sổ trống; chưa có cơ chế lời mời gia đình. Mật khẩu được băm Argon2id, không lưu dạng rõ.

## AI do chủ ứng dụng cấu hình

Tất cả tài khoản dùng `GEMINI_API_KEY` chung trên server. Đặt thêm `GEMINI_MODEL` trong biến môi trường của Render nếu muốn cố định một model cho mọi người. Khi biến này có giá trị, ứng dụng chỉ gọi model đó, không tự chuyển sang model khác nếu lỗi. Để trống giữ danh sách dự phòng hiện có. Khóa và model không do thành viên nhập; không trả khóa hoặc chuỗi kết nối database về trình duyệt. Lượt sử dụng của cả nhà dùng chung hạn mức API của chủ ứng dụng.

Trong chế độ nhiều tài khoản, các nút cấu hình kết nối được ẩn và API không cho sửa cấu hình chung. Chủ ứng dụng quản lý cấu hình ở môi trường server. Bản desktop một người dùng vẫn có màn hình cấu hình cục bộ như trước.

## Sổ đã có

Sau nâng cấp, dữ liệu hiện tại thuộc tài khoản **chuso**, dùng mật khẩu đang có. ID, số tiền, tick hoàn thành, ngày tháng và liên kết được giữ nguyên. Tài khoản mới nhận danh mục mặc định, không nhận dữ liệu của `chuso`. Tất cả thiết bị cần đăng nhập lại một lần sau nâng cấp.

Cache và hàng chờ đồng bộ có khóa theo ID người dùng. Chỉ `chuso` được chuyển hàng chờ từ bản cũ vào sổ của mình. Khi đổi tài khoản ở một tab, các tab còn lại tải lại; API từ tab cũ không được ghi vào sổ mới. Đăng xuất chặn nếu còn khoản chưa đồng bộ. Khởi động ứng dụng cần mạng để xác nhận tài khoản; sau khi đã mở sổ, hàng chờ offline vẫn hoạt động.

## Quy trình đưa lên cloud

Không chạy thay đổi schema thật trong quá trình khởi động app. Chuẩn bị và duyệt bước chuyển dữ liệu trước khi phát hành code mới.

1. Chạy `python migrate_private_ledgers.py` để xem số bản ghi; lệnh mặc định chỉ đọc. `.env.cloud` không được commit hoặc in ra.
2. Sau khi được đồng ý áp dụng vào cloud, chạy `python migrate_private_ledgers.py --apply`. Công cụ dùng `pg_dump` sao lưu schema `public` vào `output/deployment/*.dump` trước. Nếu sao lưu lỗi, dừng; không chạy migration. PostgreSQL nâng cấp trong một transaction, có khóa ngăn hai lần chạy cùng lúc và giới hạn đợi khóa 10 giây.
3. Kiểm tra báo cáo số bản ghi trước/sau. Migration gắn dữ liệu cũ cho `chuso`, tạo vai trò hạn chế, chính sách RLS và khóa ngoại kiểm tra chủ sở hữu; xóa các phiên cũ để yêu cầu đăng nhập lại. Migration chạy lại không thay đổi dữ liệu.
4. Push code đã kiểm thử lên repository SmartSpendAI, deploy dịch vụ Render hiện tại trên gói **Free**, không tạo database hoặc dịch vụ mới. Trong lúc đổi cấu trúc và phát hành có thể gián đoạn ngắn; không tạo tài khoản thành viên cho đến khi bản mới đã Live.
5. Kiểm tra `/healthz`, đăng nhập `chuso`, dữ liệu cũ và quyền truy cập. Các bài kiểm thử tạo tài khoản/giao dịch chỉ chạy trên database thử nghiệm.

Nếu migration lỗi, transaction rollback về schema trước đó. Sau khi đã migration, không chỉ rollback Docker về bản cũ vì bản cũ không hỗ trợ khóa sở hữu. Giữ bản sao lưu để phục hồi có kiểm soát nếu cần; phục hồi có thể mất các thay đổi phát sinh sau thời điểm backup.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
node tests/test_private_cache.cjs
python tests/serve_accounts_preview.py
```

Preview dùng SQLite thử nghiệm trong `output/accounts-preview`, không đọc `.env.cloud` hoặc dữ liệu thật. Dữ liệu thử được giữ lại khi khởi động lại preview. Tài khoản fixture `chuso` có mật khẩu `Only-for-isolated-browser-tests-12345`, chỉ dùng cho preview. Preview không gắn khóa AI thật.

Để kiểm thử RLS và nâng cấp schema đã có dữ liệu, cấu hình `SMARTSPEND_TEST_POSTGRES_URL` trỏ tới database **smartspend_accounts_test trên 127.0.0.1**. Bộ kiểm thử sẽ xóa và tạo lại schema `public` của database thử nghiệm này; từ chối địa chỉ khác. Cần PostgreSQL cục bộ và vai trò fixture có quyền tạo role. Bộ fixture bao gồm schema của phiên bản đã triển khai `684c081` để kiểm tra dữ liệu cũ.

SQLite cũ trên PC được sao lưu nhất quán thành `*.before_private_ledgers.db` rồi nâng cấp trong một transaction. Không chuyển SQLite sang database khác và không sửa Supabase khi chạy preview.
