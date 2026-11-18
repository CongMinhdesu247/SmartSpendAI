# Xử lý lỗi Gemini 504 khi tạo thực đơn dài — Báo cáo kỹ thuật

Thư viện `google-genai` chuyển `HttpOptions.timeout` (tính bằng mili-giây) thành cả timeout phía client lẫn header `X-Server-Timeout` gửi tới máy chủ Google. Mức 20 giây cũ quá ngắn đối với yêu cầu tạo thực đơn tuần đầy đủ nên dễ gặp `504 Deadline Exceeded`.

## Giải pháp đã áp dụng

- Tăng `HttpOptions(timeout=90000)` (90 giây) với `HttpRetryOptions(attempts=1)` trong `backend/ai_service.py` để tránh nhân đôi chi phí/độ trễ khi mạng chậm, đồng thời vẫn thấp hơn ngưỡng timeout mặc định của Cloudflare Tunnel.
- Kiểm chứng bằng unit test offline xác nhận header `X-Server-Timeout: 90` và `attempts == 1`.
