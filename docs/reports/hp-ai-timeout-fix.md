# Gemini trả 504 khi tạo thực đơn dài — 17/11/2026

HP đã xác nhận schema mới được nạp và yêu cầu thử một mục trả GEMINI_OK. Yêu cầu thật tạo kế hoạch trả ServerError / 504 từ Gemini; app chuyển thành HTTP 502. google-genai chuyển HttpOptions.timeout=20000 thành cả timeout phía client lẫn header X-Server-Timeout: 20 gửi Google. Đây là deadline quá ngắn cho yêu cầu dài; tăng lên 90000 ms (90 giây). Vẫn một attempt, không thêm retry khi timeout, không đổi model hay key. Từng lần gọi vẫn có giới hạn hữu hạn; model dự phòng chỉ được gọi khi nhận 404.

Đã kiểm tra offline bằng SDK thật: request gửi Google có header X-Server-Timeout: 90 và retry attempts vẫn bằng 1. Chưa kiểm chứng yêu cầu thực đơn thật trên HP sau thay đổi này; Google hoặc đường mạng vẫn có thể gặp lỗi ngay cả khi tăng deadline.

## Cập nhật ngay trên HP

Trong phiên SSH, chạy từng lệnh:

```bash
cd /home/congminh/apps/SmartSpendAI
cp backend/ai_service.py /home/congminh/ai_service.before-timeout-fix.py
sed -i 's/timeout=20000/timeout=90000/' backend/ai_service.py
grep -n 'timeout=' backend/ai_service.py
docker compose build web
docker compose up -d --no-deps --force-recreate --wait web
```

grep phải hiện timeout=90000; nếu không có dòng đó thì dừng trước build. Không sửa .env, database hay tunnel. Source trong workspace PC cũng đã được đổi tương ứng để các lần đóng gói sau giữ bản sửa.

Xác minh container bằng SDK thật, không gọi Gemini hoặc đọc key:

```bash
docker compose exec -T web python - <<'PY'
from backend.ai_service import make_client
with make_client('offline-test-not-a-real-key') as client:
    request = client._api_client._build_request('POST', 'models/fixture:generateContent', {})
    print('GOOGLE_DEADLINE_SECONDS:', request.headers.get('X-Server-Timeout'))
PY
```

Phải hiện 90. Sau đó thử tạo kế hoạch cũ một lần, cho phép chờ đến khoảng 90 giây; không bấm gửi liên tục. Nếu vẫn lỗi, thu log mới để kiểm tra loại lỗi và status. Không xem việc sửa timeout là bằng chứng yêu cầu thật đã thành công.

Tham khảo: [Gemini deadline_exceeded](https://ai.google.dev/gemini-api/docs/api-errors), [Google GenAI timeout header](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py).
