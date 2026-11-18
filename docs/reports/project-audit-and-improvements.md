# Báo cáo Kiểm toán Toàn diện & Hồ sơ Nâng cấp SmartSpend Pro

> **Ngày kiểm toán:** 18/11/2026  
> **Phạm vi kiểm toán:** Toàn bộ mã nguồn `SmartSpendAI` — bao gồm **Bảo mật (Security)**, **Tính năng & Logic nghiệp vụ (Features & Business Logic)**, **Cấu trúc cây thư mục & Sắp xếp mã nguồn (Directory Tree & Architecture)**, **Giao diện & Sức hút người dùng (UI/UX Pro)**, và **Cấu hình Cập nhật Local Server (`SERVER_CONTEXT.md`)**.

---

## Phần 1 — Toàn bộ các điểm trừ / chưa ổn đã phát hiện & lưu lại

### 1. Về Bảo mật (Security Findings)

| Mã | Mức độ | Điểm chưa ổn phát hiện | Vị trí tệp | Tác động & Rủi ro |
| :--- | :---: | :--- | :--- | :--- |
| **SEC-01** | **Cao** | **Bypass tài khoản `chuso` bị vô hiệu hóa & rò rỉ thời gian xác thực (Timing Side-Channel):** Truy vấn cũ lọc `Account.filter_by(active=True)` rồi rơi về nhánh dự phòng `settings.password_hash` trong `.env` khi trả về `None`; đồng thời tạo mới `dummy_hash` Argon2 lặp lại mỗi lần khởi tạo router gây tốn CPU không cần thiết. | `backend/routers/auth.py`, `backend/access.py` | Tài khoản quản trị bị khóa trong DB vẫn đăng nhập được bằng mật khẩu môi trường cũ; chênh lệch thời gian phản hồi khi dò tên tài khoản. |
| **SEC-02** | **Cao** | **Giả mạo `CF-Connecting-IP` vượt qua Rate Limit khi đứng sau Nginx / Caddy trực tiếp:** `extract_client_ip` ưu tiên đọc `cf-connecting-ip` trước `x-real-ip`, trong khi cấu hình mẫu Nginx/Caddy chưa xóa header `CF-Connecting-IP` từ phía client và `LoginLimiter` cũ cộng dồn cả lượt đăng nhập hợp lệ. | `backend/access.py`, `deploy/local-server/sites/*` | Kẻ tấn công gọi thẳng vào Nginx/Caddy có thể gửi `CF-Connecting-IP` ngẫu nhiên ở mỗi request để vô hiệu hóa hoàn toàn giới hạn chống brute-force mật khẩu; hoặc khóa nhầm toàn bộ người dùng chung IP gateway. |
| **SEC-03** | **Cao** | **Vượt giới hạn kích thước Request Body bằng `Transfer-Encoding: chunked`:** Tầng middleware chỉ kiểm tra header `Content-Length`. Nếu kẻ tấn công gửi luồng dữ liệu dạng chunked (bỏ trống `Content-Length`), FastAPI vẫn đọc toàn bộ nhiều chục/trăm MB vào RAM. | `backend/access.py` | Gây cạn kiệt bộ nhớ (OOM kill) trên container giới hạn 768 MiB RAM của Local Server. |
| **SEC-04** | **Trung bình - Cao** | **Mở khóa bộ nhớ đệm ngoại tuyến (Offline PWA) không giới hạn tuổi thọ & sót `sessionStorage`:** Lưu mốc `smartspend-auth-seen` nhưng không kiểm tra hạn 30 ngày khi mất mạng; `clearPrivateCache()` chưa dọn trạng thái điều hướng trong `sessionStorage`. | `frontend/auth.js` | Thiết bị dùng chung đã hết hạn phiên từ lâu vẫn có thể ngắt mạng để xem lại dữ liệu cache cũ. |
| **SEC-05** | **Trung bình** | **Tích tụ không giới hạn phiên đăng nhập (`AccessSession`) & nguy cơ lỗi `500` ở `/logout-all`:** Một tài khoản đăng nhập trên nhiều trình duyệt không giới hạn số phiên hoạt động song song; `/api/auth/logout-all` thiếu kiểm tra `database.engine` và `request.state.user` khác `None`. | `backend/routers/auth.py` | Phình bảng phiên trong DB và kéo dài bề mặt rủi ro khi quên đăng xuất trên thiết bị lạ. |
| **SEC-06** | **Trung bình** | **Khóa nhầm quản trị viên khi khai báo `SMARTSPEND_ALLOWED_HOSTS` dạng URL & thiếu `Cache-Control: no-cache` cho HTML gốc:** Nếu điền `https://192.168.1.50:8092/` vào `SMARTSPEND_ALLOWED_HOSTS`, chuỗi không khớp với header `Host`; ngoài ra `/` và `/index.html` chưa đặt `no-cache` khiến PWA giữ vỏ HTML cũ sau khi cập nhật server. | `backend/access.py`, `Dockerfile.hp` | Trả lỗi `400` khi mở qua LAN/Tailscale; trình duyệt chậm nhận bản cập nhật bảo mật mới; `Dockerfile.hp` cứng `--no-proxy-headers` làm mất nhận diện scheme `https` sau Reverse Proxy. |
| **SEC-07** | **Trung bình** | **Thiếu cấu hình chống khóa SQLite (`busy_timeout`) & loại trừ `.db-wal`/`.db-shm` khi đóng gói:** SQLite cục bộ chưa đặt `PRAGMA busy_timeout=5000`; lệnh `rsync` / đóng gói cần chặn triệt để cả tệp nhật ký WAL/SHM. | `backend/database.py`, `scripts/homeserver/package.py` | Dễ gặp lỗi `database is locked` khi ghi nhanh liên tiếp trên Desktop; nguy cơ chép nhầm tệp tạm SQLite lên server. |

---

### 2. Về Tính năng & Logic nghiệp vụ (Feature & Logic Findings)

| Mã | Mức độ | Điểm chưa ổn phát hiện | Vị trí tệp | Tác động thực tế |
| :--- | :---: | :--- | :--- | :--- |
| **FEAT-01** | **Cao** | **Lỗi ngắt kết nối giả (Timeout 15 giây) khi gọi Cố vấn Tài chính AI (`/api/finance/ai-review`):** Hàm `financeApi()` đặt cứng `AbortController` 15.000ms cho mọi API và gom chung `AbortError` thành lỗi mất mạng (`error.network = true`), trong khi Gemini AI cần tới 15–35 giây để phân tích sâu. | `frontend/finance.js` | Cố vấn AI đang phân tích dở bị trình duyệt tự hủy ở giây thứ 15 và báo sai *"Chưa kết nối được máy chủ"*. |
| **FEAT-02** | **Cao** | **Sao lưu JSON trước đây thiếu thực thể quan trọng:** Cần đảm bảo chuẩn Sao lưu/Khôi phục JSON v2 bao phủ trọn vẹn cả 7 nhóm dữ liệu (Danh mục, Giao dịch, Ngân sách, Khoản định kỳ, Mục tiêu + Đóng góp, Kế hoạch + Hạng mục, Sở thích) kèm chống trùng lặp (idempotent). | `backend/services/backup.py`, `frontend/finance.js` | Bảo toàn 100% tài sản dữ liệu cá nhân khi chuyển máy hoặc khôi phục sổ. |
| **FEAT-03** | **Trung bình - Cao** | **Thiếu góc nhìn Xu hướng Đa tháng (6 tháng) & Dự báo Cuối tháng (Burn-Rate Projection):** Ứng dụng chỉ xem từng tháng đơn lẻ, chưa dự báo tổng chi cuối tháng theo tốc độ tiêu tiền hiện tại và chưa có biểu đồ so sánh Thu — Chi — Tiết kiệm ròng qua 6 tháng. | `backend/services/insights.py`, `backend/routers/finance.py`, `frontend/finance.js` | Người dùng không thấy trước nguy cơ vỡ ngân sách cuối tháng và khó đánh giá đà tích lũy dài hạn. |
| **FEAT-04** | **Trung bình** | **Phải nhập lại hạn mức ngân sách thủ công mỗi đầu tháng mới:** Chưa có tính năng kế thừa / sao chép nhanh bộ ngân sách (tổng tháng & từng danh mục) từ tháng liền trước. | `backend/routers/finance.py`, `frontend/finance.js` | Tốn thời gian thao tác lặp lại hàng tháng; thẻ Ngân sách trống hiển thị `—` kém trực quan. |
| **FEAT-05** | **Trung bình** | **Thiếu tính toán nhịp độ tiết kiệm cần thiết cho Mục tiêu & tổng cam kết cố định tháng:** Thẻ Mục tiêu chỉ hiện `%` mà chưa tính cần để dành bao nhiêu tiền mỗi tháng để kịp hạn (`deadline`); tab Định kỳ chưa quy đổi tổng chi phí cố định bình quân/tháng; banner hóa đơn đến hạn thiếu nút thanh toán 1 chạm. | `backend/services/insights.py`, `frontend/finance.js` | Giảm tính hành động (actionability) khi lập kế hoạch tài chính cá nhân. |
| **FEAT-06** | **Thấp - Trung bình** | **NLP tiếng Việt thiếu từ lóng phổ biến, thiếu Nhân bản giao dịch & lỗi nhãn nút Ẩn mục đã mua:** Chưa hiểu `50 cành` (`50.000₫`), `2 lít` (`200.000₫`), `1 củ 5` có khoảng trắng; sửa giao dịch chưa có nút *"Nhân bản cho hôm nay"*; nút *"Ẩn đã mua"* ở danh sách đi chợ bị đổi thành *"Ẩn đã xong"* khi bật/tắt lại. | `frontend/finance.js`, `frontend/app.js` | Ảnh hưởng độ mượt và tính bản địa hóa tiếng Việt. |

---

### 3. Về Cấu trúc cây thư mục, Sắp xếp mã nguồn & Local Server

| Mã | Mức độ | Điểm chưa ổn phát hiện | Vị trí tệp | Giải pháp chuẩn hóa |
| :--- | :---: | :--- | :--- | :--- |
| **ARCH-01** | **Trung bình - Cao** | **File `backend/routers/finance.py` phình to (~1.285 dòng) ôm đồm cả tầng tính toán & sao lưu:** Logic chấm điểm sức khỏe tài chính, dự báo xu hướng và toàn bộ trình xuất/nhập dữ liệu V2 nằm lẫn với các HTTP route handlers. | `backend/routers/finance.py`, `backend/services/` | Tách tầng nghiệp vụ sạch sẽ sang `backend/services/insights.py` và `backend/services/backup.py`; router chỉ làm nhiệm vụ điều phối HTTP gọn nhẹ. |
| **ARCH-02** | **Thấp** | **Rác `.pyc` mồ côi từ các file cũ đã di chuyển:** Thư mục `__pycache__/` ở gốc và `tests/__pycache__/` còn lưu bytecode của các script cũ đã xóa (`configure_cloud`, `desktop_launcher`, `serve_preview`...). | Thư mục gốc, `tests/` | Dọn sạch toàn bộ `.pyc` mồ côi và đồng bộ chuẩn kiểm tra cây thư mục. |
| **ARCH-03** | **Cao** | **Rủi ro xung đột tên Compose Project & lỗi di chuyển script đang chạy khi cập nhật Local Server:** `deploy/local-server/docker-compose.yml` từng đặt `name: smartspend` lệch với `name: smartspend-hp` đang chạy sẵn trên server (dễ gây đụng cổng `127.0.0.1:8092`); `update.sh` chưa bọc hàm `main()` trước khi `mv` thư mục lúc nâng cấp bố cục. | `deploy/local-server/docker-compose.yml`, `scripts/homeserver/update.sh`, `deploy_update.ps1` | Đồng bộ `name: ${SMARTSPEND_COMPOSE_PROJECT:-smartspend-hp}`, bọc `main() { ... }; main "$@"` trong `update.sh`, kiểm tra `pg_restore --list` trước khi dừng DB, tự động hoàn trả bố cục nếu lỗi, và thêm chế độ `-CheckOnly` cho `deploy_update.ps1`. |

---

## Phần 2 — Tổng hợp các cải tiến chuyên nghiệp đã hoàn thiện trong `SmartSpendAI`

### 1. Kiến trúc & Bảo mật Chiều sâu (Defense-in-Depth)
- **Chống tràn bộ nhớ Chunked Stream (`_make_bounded_receive`):** Đếm byte thực tế trực tiếp trên luồng ASGI `receive`, ngắt ngay lập tức với mã `413 Payload Too Large` nếu vượt ngưỡng (`256 KiB` mặc định, `5 MiB` cho `/api/finance/import`), bất kể có gửi `Content-Length` hay không.
- **Nhận diện IP thật chống giả mạo sau Proxy (`extract_client_ip` + Nginx/Caddy Hardening):** Ưu tiên `X-Real-IP` do Nginx/Caddy nội bộ gán (kèm xóa `CF-Connecting-IP` giả mạo ở tầng Proxy), tự động rơi về `CF-Connecting-IP` khi đi qua Cloudflare Tunnel, hoàn trả hạn mức khi đăng nhập đúng (`refund_success`), và giới hạn tối đa 10 phiên hoạt động mỗi người dùng (`MAX_SESSIONS_PER_USER`).
- **Tách tầng `backend/services/`:** Tổ chức rõ ràng `backend/routers/{auth,finance,plans,system}.py`, `backend/services/{insights,backup}.py`, `backend/schemas/{access,ai,finance,plans}.py`.

### 2. Trải nghiệm Sản phẩm & Giao diện Fintech Chuyên nghiệp (UI/UX Pro)
- **Bảng Lệnh Nhanh Spotlight (`Ctrl+K` / `⌘K` — Command Palette):** Tìm kiếm không dấu tức thì mọi thao tác trong ứng dụng — hoặc gõ thẳng câu chi tiêu (`35k5 phở bò`) ngay trong hộp lệnh `Ctrl+K` để ghi sổ tức thì!
- **Điểm Sức Khỏe Tài Chính 0–100 kèm 4 Trụ cột Minh bạch:** Hiển thị vòng tròn điểm số kèm thanh chi tiết 4 trụ cột (*Kỷ luật ngân sách /40*, *Tiết kiệm ròng /30*, *Hóa đơn đúng hạn /15*, *Nhịp chi ổn định /15*) và chuỗi **Ngày không chi tiêu (0₫)**.
- **Biểu đồ Kép: Nhịp Lũy Kế Tháng ↔ Xu Hướng 6 Tháng + Dự báo Cuối tháng:** Chuyển đổi mượt mà giữa đường chi ròng lũy kế từng ngày và biểu đồ cột Thu — Chi — Tích lũy ròng 6 tháng gần nhất, kèm con số dự báo tổng chi cuối tháng theo tốc độ hiện tại.
- **Cố vấn Tài chính AI có Trọng tâm (Focus Presets) & Timeout 95s chuẩn xác:** Cho phép chọn trọng tâm tư vấn (*Tổng quan*, *Giảm ăn ngoài*, *Tiết kiệm 20%*, *Phanh mua sắm*) trước khi Gemini AI đọc bức tranh tài chính tháng.
- **Tiện ích Thực chiến Hàng ngày:**
  - **Lịch Nhiệt độ Chi tiêu (Interactive Heatmap Calendar)** chạm ngày để lọc giao dịch + **Biểu đồ Doughnut Cơ cấu Danh mục**.
  - **Sao chép hạn mức ngân sách từ tháng trước** chỉ với 1 cú nhấp (`POST /api/finance/budgets/{month}/copy-previous`).
  - **Thanh toán nhanh 1 chạm** ngay trên banner cảnh báo hóa đơn sắp đến hạn/quá hạn & quy đổi tổng cam kết cố định/tháng.
  - **Tính tốc độ tích lũy mục tiêu** (*Cần dành ~X ₫/tháng để kịp hạn*) & huy hiệu hoàn thành mục tiêu.
  - **Nhân bản giao dịch cho hôm nay** 1 chạm, NLP tiếng Việt hiểu cả `35k5`, `1tr5`, `50 cành`, `2 lít`, ngày `DD/MM`, cùng hỗ trợ cài đặt PWA trực tiếp (`beforeinstallprompt` + App Shortcuts).

### 3. Sẵn sàng Cập nhật An toàn lên Local Server (`SERVER_CONTEXT.md`)
- Trọn bộ cấu hình tại `deploy/local-server/` (`docker-compose.yml` cô lập mạng DB `internal: true`, container `read_only: true`, bind `127.0.0.1:8092`, mount bền vững `./data/postgres` và `./data/backups`, kèm cấu hình mẫu `_proxy/sites/` cho Nginx, Caddy, Cloudflare Tunnel).
- Trình cập nhật 1 lệnh `scripts/homeserver/deploy_update.ps1` + `scripts/homeserver/update.sh`: Tự động nhận diện bố cục hiện hữu trên server, sao lưu PostgreSQL trước khi nâng cấp, kiểm tra `/healthz` thực thi `SELECT 1`, và tự động rollback image nếu xảy ra sự cố.
