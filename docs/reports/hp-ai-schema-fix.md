# Sửa lỗi Gemini schema quá phức tạp — Báo cáo kỹ thuật

Google trả HTTP 400 (`INVALID_ARGUMENT: The specified schema produces a constraint that has too many states for serving`) khi gửi JSON Schema lồng nhau kèm nhiều ràng buộc `minLength`/`maxLength`/`minimum`/`maximum`.

## Giải pháp đã áp dụng

- Lọc bỏ các từ khóa giới hạn độ dài/khoảng số trong bản schema gửi tới Gemini (`_gemini_plan_schema()`), giữ nguyên cấu trúc kiểu dữ liệu, trường bắt buộc và `enum`.
- Dữ liệu trả về từ AI vẫn được kiểm tra đầy đủ mọi giới hạn thông qua `AIPlanOutput.model_validate` trước khi lưu vào cơ sở dữ liệu.
- Giao diện xử lý an toàn các phản hồi lỗi HTTP phi-JSON từ reverse proxy/tunnel.

## Quy trình cập nhật lên Home Server

```bash
cd ~/apps/SmartSpendAI
bash scripts/homeserver/backup.sh
docker image tag smartspend-hp-app:local smartspend-hp-app:before-ai-fix
tar -xzf ~/SmartSpendAI-hp.tar.gz
docker compose build web
docker compose up -d --no-deps --wait web
curl --fail http://127.0.0.1:8092/healthz
```
