# Chi tiêu, kế hoạch và tiết kiệm

Mở lại `run_app.bat` sau khi cập nhật. Các bảng dữ liệu mới được tạo khi backend khởi động; không cần Node.js để chạy app. Nếu dùng bản `.exe`, đóng gói lại bằng `build_exe.bat`.

## Bốn màn hình

- **Chi tiêu:** tổng quan tháng, ngân sách chung và theo danh mục, thu/chi, tìm kiếm và xuất CSV.
- **Kế hoạch AI:** thực đơn, đi chợ và lịch trình; sao chép, nguyên liệu sẵn có, sở thích mặc định và đổi một mục bằng AI.
- **Định kỳ:** lịch các khoản cần trả, nhắc hạn trong app và xác nhận thanh toán.
- **Mục tiêu:** ghi nhận tiền dành riêng, tiến độ và lịch sử đóng góp.

## Ghi giao dịch

Nhập `35k ăn sáng`, `1,5tr tiền nhà` hoặc `35.000 ăn sáng` vào ô thêm nhanh. App điền gợi ý để bạn kiểm tra số tiền, danh mục và ngày trước khi xác nhận. Đây là phân tích cú pháp cục bộ, không gửi nội dung cho AI.

Nút **Thêm giao dịch** dùng được ở mọi màn hình. Chọn **Khoản thu** để ghi thu nhập. Bấm tên giao dịch để sửa; bấm xóa và chọn **Hoàn tác** trong thông báo nếu cần khôi phục. Thông báo hoàn tác hiển thị 10 giây.

Ngân sách là hạn mức bạn đặt, không phải số dư ngân hàng. Tiền dành cho mục tiêu không tự trừ khỏi ngân sách chi tiêu và không thực hiện chuyển tiền.

Màn hình tháng có tìm theo nội dung (hỗ trợ không dấu), lọc danh mục/thu/chi và phân trang. Xuất CSV áp dụng cho tháng và bộ lọc đang chọn, gồm tất cả các trang kết quả.

## Kế hoạch và thanh toán

- Tích checkbox ở hạng mục có giá sẽ tự ghi một khoản chi vào ngày hiện tại (giờ Việt Nam), cập nhật mức đã chi và biểu đồ kế hoạch, đồng thời cập nhật báo cáo tháng tương ứng. Mục giá 0 chỉ đánh dấu hoàn thành.
- Bỏ tích hủy khoản chi do checkbox tự tạo; tích lại khôi phục cùng giao dịch, không cộng trùng.
- Ô giá là giá dự kiến; khi mục đã được ghi chi tự động bằng checkbox, sửa ô giá cũng cập nhật số tiền của khoản chi tự động.
- **Ghi chi** mở giao dịch thực tế, cho phép sửa số tiền và ngày thanh toán.
- **Đã ghi chi** mở lại giao dịch liên kết. Khoản nhập thủ công bằng **Ghi chi** không bị sửa hoặc xóa khi đổi checkbox hay giá dự kiến.
- Một hạng mục có một giao dịch liên kết; các lần gửi lại không tạo khoản chi trùng.
- Sao chép kế hoạch tạo bản mới chưa hoàn thành, chưa thanh toán.
- Xóa kế hoạch giữ các giao dịch thực tế trong sổ chi tiêu. Hoàn tác khôi phục liên kết với giao dịch, không ghi tiền lần nữa.
- Các dấu tích có từ bản cũ không tự sinh giao dịch khi mở app. Để ghi chi cho mục cũ chưa có giao dịch, bỏ tích rồi tích lại hoặc dùng **Ghi chi**.
- Lịch sử tải 30 kế hoạch mỗi trang; dùng **Tải thêm kế hoạch** để xem tiếp. Bộ lọc thực đơn/đi chơi áp dụng trên máy chủ.

Đổi một mục bằng AI chỉ áp dụng cho mục chưa có thanh toán. Khi đổi thực đơn, app không tự cập nhật các nguyên liệu khác: cần kiểm tra lại giỏ đi chợ. Giá AI là ước tính, không phải giá bán được xác minh trực tiếp.

## Khoản định kỳ

Ngày đến hạn và ngày thanh toán là hai thông tin riêng. **Ghi thanh toán** tạo giao dịch và chuyển lịch sang kỳ tiếp theo. Không tự tạo khoản chi khi đến hạn.

Lịch hằng tháng giữ ngày gốc: ngày 31 chuyển về cuối tháng ngắn và quay lại ngày 31 ở tháng phù hợp. Nhắc hạn nằm trong app, chưa có thông báo đẩy/email. Lưu trữ khoản định kỳ không xóa lịch sử thanh toán.

## Ngoại tuyến

Sau lần mở trực tuyến, app lưu bản xem gần nhất và các tài nguyên giao diện cục bộ. Giao dịch mới nhập khi mất kết nối được lưu trên thiết bị, hiện trong nhóm **Chờ đồng bộ** và chưa tính vào báo cáo. App thử gửi lại khi có mạng hoặc khi bấm **Thử đồng bộ**. Mỗi khoản có mã riêng để chống gửi trùng.

Chỉ hỗ trợ xếp hàng **giao dịch mới nhập thủ công**. Sửa giao dịch, thanh toán kế hoạch/định kỳ, mục tiêu và các thao tác AI cần kết nối máy chủ. Không đổi cơ sở dữ liệu khi còn khoản chờ đồng bộ.

Tải lại app ngoại tuyến đầy đủ cần Service Worker: dùng HTTPS hoặc localhost. Safari qua địa chỉ LAN HTTP không cung cấp đầy đủ khả năng này; cần giữ tab đang mở để tiếp tục nhập khi mất kết nối. Xóa dữ liệu trình duyệt có thể xóa các khoản chưa đồng bộ.

PWA không tự biến máy tính thành máy chủ trên Internet. Đồng bộ qua LAN vẫn cần máy tính chạy app và cùng mạng. Để dùng khi máy tính tắt, xem [hosting và đăng nhập cloud](iphone-cloud.md). Bản cloud hỗ trợ [tài khoản và sổ riêng](private-accounts.md).

## Dữ liệu cũ và nâng cấp

Schema bổ sung các bảng `spend_categories`, `spend_transactions`, `spend_budgets`, `spend_recurring`, `spend_goals`, `spend_contributions`, `spend_preferences`, `spend_plan_archive`. Giữ nguyên cột, giá và checkbox của `plans`/`plan_items`.

Trước lần nâng cấp SQLite đầu tiên, app tự tạo bản sao nhất quán `smartspend_local.before_finance_v1.db` cạnh file dữ liệu. Bản sao có sẵn không bị ghi đè.

**Các checkbox/số đã chi theo cách tính cũ không tự chuyển thành giao dịch.** Dữ liệu cũ không có ngày thanh toán đáng tin cậy. Số “Đã chi” mới của kế hoạch chỉ tính các giao dịch đã ghi; nếu cần đưa khoản cũ vào báo cáo, dùng **Ghi chi** và chọn ngày phù hợp. Cột số liệu cũ vẫn được giữ trong database.

Với PostgreSQL/Supabase, dùng cách kết nối SQLAlchemy trực tiếp hiện có. Các bảng mới bật RLS và không có policy công khai; backend cần vai trò database owner phù hợp. Không thêm quyền Data API cho `anon`/`authenticated`. Không chạy migration hoặc truy vấn thử trên dự án đám mây trong quá trình kiểm tra bản này.

Schema mới có tính bổ sung và lặp lại an toàn theo quy trình `metadata.create_all` của dự án. Để quay lại phiên bản cũ, dừng app và giữ bản dữ liệu hiện tại trước khi dùng bản SQLite sao lưu; các giao dịch mới sau thời điểm sao lưu sẽ không nằm trong bản cũ.

## Phát triển và kiểm tra

```powershell
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
npm ci
npm run build:css
```

CSS Tailwind đã được biên dịch trong `frontend/tailwind.css`. Khi đổi các utility class trong HTML/JS, chạy lại `npm run build:css`. Chart.js 4.4.2 và SVG Lucide được lưu cục bộ kèm giấy phép; font có fallback hệ thống.

```powershell
python tests/serve_preview.py
```

Lệnh này tạo backend thử nghiệm tại `http://127.0.0.1:8767`, với dữ liệu minh họa và cơ sở dữ liệu tạm riêng. Không đọc/sửa cấu hình hoặc dữ liệu thật. API AI trong kiểm tra tự động dùng phản hồi mô phỏng; chưa xác minh chất lượng đề xuất qua Gemini thật. Schema PostgreSQL được kiểm tra biên dịch, chưa chạy tích hợp trên một máy chủ PostgreSQL.
# Biểu đồ thu chi trong tháng

Đường biểu diễn chi ròng lũy kế từ đầu tháng: tổng chi trừ tổng thu, chốt cuối mỗi ngày. Ghi chi làm đường tăng, nhận tiền làm đường giảm; tiền thu lớn hơn tiền chi có thể đưa đường xuống dưới 0. Các ngày chưa tới không được dự đoán. Nếu bạn đã ghi giao dịch có ngày trong tương lai, biểu đồ vẫn thể hiện dữ liệu đã ghi đó.

Ngân sách toàn tháng là đường ngang nét đứt. Chỉ phần đường cao hơn ngân sách được tô đỏ; khi tiền thu kéo chi ròng xuống dưới hạn mức, đoạn đường mới trở về màu tím. Ngân sách từng danh mục không thay thế đường giới hạn toàn tháng. Nếu chưa đặt ngân sách, bấm **Đặt ngân sách** dưới biểu đồ để bật cảnh báo. Thẻ **Đã chi** và **Còn trong ngân sách** phía trên vẫn thống kê tổng chi thực tế, chưa trừ thu; biểu đồ thể hiện chi ròng và có nhãn riêng.
