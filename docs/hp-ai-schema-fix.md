# Sửa lỗi Gemini schema quá phức tạp — 17/11/2026

Google trả HTTP 400 / INVALID_ARGUMENT: "The specified schema produces a constraint that has too many states for serving" khi gọi gemini-3.5-flash với schema kế hoạch hiện tại. Backend chuyển thành 502; giao diện có thể nhận HTML từ proxy và hiện lỗi phân tích JSON.

Bản sửa bỏ các giới hạn min/max độ dài, số phần tử và khoảng số khỏi schema gửi tới Gemini. Kiểu dữ liệu, trường bắt buộc, enum và mô tả vẫn giữ. Kết quả vẫn phải qua AIPlanOutput.model_validate với đầy đủ giới hạn trước khi lưu vào DB. Áp dụng chung cho tạo kế hoạch và đổi hạng mục. Không đổi model, key, quota hay schema database. Gói cập nhật trên PC đã bổ sung deadline 90 giây sau khi HP ghi nhận lỗi Gemini 504; xem [bản sửa timeout](hp-ai-timeout-fix.md).

Giao diện xử lý phản hồi không phải JSON của hai chức năng AI bằng thông báo tiếng Việt có HTTP status. Cache PWA tăng lên v14 để tải bản giao diện mới.

Đã kiểm tra 6 tests AI, gồm schema truyền cho SDK không có giới hạn phức tạp và backend vẫn từ chối danh sách rỗng/quá 200 mục, tên quá dài, giá âm/quá giới hạn. Các tests JavaScript gồm phản hồi HTML 502 và JSON lỗi đều đạt. Docker Desktop không hoạt động trong lượt sửa nên chưa build lại image Linux; chưa thử API thật trên HP với bản sửa. Cần build và thử trên HP.

## Cập nhật

PowerShell trên PC, không phải shell HP:

```powershell
cd C:\Users\ADMIN\Downloads\SmartSpendAI
scp .\output\deployment\SmartSpendAI-ai-fix.tar.gz congminh@100.95.33.63:/home/congminh/SmartSpendAI-ai-fix.tar.gz
```

Shell SSH trên HP, chạy từng lệnh; nếu lỗi thì dừng:

```bash
cd /home/congminh/apps/SmartSpendAI
bash scripts/homeserver/backup.sh
docker image tag smartspend-hp-app:local smartspend-hp-app:before-ai-fix
tar -xzf /home/congminh/SmartSpendAI-ai-fix.tar.gz
docker compose build web
docker compose up -d --no-deps --wait web
curl --fail http://127.0.0.1:8092/healthz
```

Gói chỉ chứa backend/ai_service.py và 4 file giao diện app.js, finance.js, index.html, sw.js. Không thay .env, DB, Compose hoặc tunnel. Không cần migration hay restart DB. Làm mới trình duyệt bằng Ctrl+Shift+R rồi thử lại tạo kế hoạch một lần.

Nếu cần rollback runtime (không thay dữ liệu):

```bash
SMARTSPEND_IMAGE_TAG=before-ai-fix docker compose up -d --no-deps --force-recreate --wait web
```

Lệnh rollback trên chọn image cho lần chạy đó; các lệnh sau mặc định lại dùng tag local nếu .env chưa đổi. Nếu chưa thành công, lấy log mới để xác định lỗi tiếp theo; không tiếp tục thay model/key khi chưa có bằng chứng.

Tham khảo: [Gemini structured outputs và giới hạn độ phức tạp schema](https://ai.google.dev/gemini-api/docs/structured-output).
