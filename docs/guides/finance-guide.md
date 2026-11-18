# Hướng dẫn sử dụng Sổ chi tiêu, Kế hoạch & Tiết kiệm

## Cấu trúc điều hướng & Phím tắt

- **Thanh đầu trang:** Chuyển đổi nhanh giao diện **Sáng / Tối (Dark Mode)** và nút **Ghi thu/chi** (luôn sẵn sàng ở mọi màn hình).
- **3 khu vực chính:**
  - **Sổ chi tiêu:** Thanh nhập nhanh tự nhiên, tổng quan thu/chi, nhịp đập sức khỏe tài chính, biểu đồ chi ròng lũy kế và danh sách giao dịch.
  - **Kế hoạch:** Gồm 3 mục con **Kế hoạch & AI**, **Định kỳ** và **Tiết kiệm**.
  - **Tài khoản:** Cài đặt kết nối AI/DB, mã QR cài đặt iPhone, sở thích mặc định, sao lưu/nhập dữ liệu, kho lưu trữ & thùng rác, đổi mật khẩu và quản lý phiên đăng nhập.
- **Phím tắt trên máy tính:** Nhấn `N` để mở hộp thoại ghi thu/chi mới; nhấn `/` để mở nhanh ô tìm kiếm giao dịch.

## Nhập nhanh ngôn ngữ tự nhiên (0ms, không tốn AI)

Tại đầu màn hình **Sổ chi tiêu**, bạn có thể gõ tự nhiên và nhấn `Enter`:

- `35k phở bò` → Khoản chi `35.000 ₫`, danh mục `Ăn uống`, ngày hôm nay.
- `1,5tr tiền nhà` → Khoản chi `1.500.000 ₫`, danh mục `Nhà ở`.
- `+15tr lương tháng 11` → Khoản thu `15.000.000 ₫`.
- `45k cà phê hôm qua` → Khoản chi `45.000 ₫`, tự động lùi ngày về hôm qua.

Thanh xem trước bên dưới sẽ hiển thị tức thì số tiền, loại giao dịch, danh mục gợi ý và ngày trước khi bạn nhấn **Ghi ngay** hoặc **Chi tiết**.

## Kế hoạch AI, Kế hoạch Thủ công & Đồng bộ hai chiều

- Bạn có thể tạo kế hoạch tự động bằng **Gemini AI** hoặc bấm **Tạo thủ công** để tự lập danh sách đi chợ / lịch trình mà không cần API key.
- Hỗ trợ đầy đủ thao tác **Sửa thông tin kế hoạch**, **Thêm hạng mục mới**, **Sửa nội dung / giá từng mục**, **Đổi 1 mục bằng AI** và **Xóa mục**.
- **Đồng bộ hai chiều với Sổ chi tiêu:**
  - Tích chọn hoàn thành mục có giá (hoặc bấm **Ghi chi** để nhập ngày/giá thực tế) đều đánh dấu hoàn thành hạng mục và cập nhật vào báo cáo tháng.
  - Nếu bạn xóa giao dịch liên kết trong Sổ chi tiêu, dấu hoàn thành của hạng mục tương ứng tự động được bỏ tích; khi khôi phục giao dịch, dấu hoàn thành được bật lại.
  - Khi xóa kế hoạch, bạn có thể chọn giữ lại hoặc hủy luôn các khoản chi tự động của kế hoạch đó.

## Khoản định kỳ, Thùng rác & Sao lưu

- **Khoản định kỳ:** Khi ghi thanh toán, lịch tự động nhảy sang kỳ tiếp theo. Nếu bạn xóa nhầm giao dịch thanh toán đó, ngày đến hạn sẽ tự động lùi về kỳ cũ và cho phép thanh toán lại bình thường.
- **Kho lưu trữ & Thùng rác:** Mọi giao dịch đã xóa, kế hoạch đã xóa, danh mục/khoản định kỳ/mục tiêu đã lưu trữ đều có thể xem lại, khôi phục hoặc xóa vĩnh viễn bất kỳ lúc nào tại **Tài khoản → Kho lưu trữ & Thùng rác**.
- **Sao lưu & Nhập dữ liệu:** Hỗ trợ xuất CSV theo tháng hoặc cả năm, tải bản sao lưu JSON toàn bộ sổ và nhập lại từ file `.json` hoặc `.csv` (tự động chống trùng lặp).

## Chế độ Ngoại tuyến (Offline PWA)

Sau khi đã đăng nhập ít nhất một lần trên thiết bị, nếu mở lại ứng dụng khi mất mạng (ví dụ trên iPhone PWA ở khu vực mất sóng), ứng dụng tự động mở khóa chế độ ngoại tuyến từ dữ liệu cache cục bộ và cho phép ghi tiếp giao dịch mới vào hàng đợi **Chờ đồng bộ**. Ngay khi có mạng trở lại, ứng dụng tự xác thực phiên và đồng bộ dữ liệu lên máy chủ.
