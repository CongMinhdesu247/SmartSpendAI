# Triển khai & Cập nhật SmartSpend Pro trên Local / Home Server (Docker Compose)

Hướng dẫn chuẩn hóa triển khai và cập nhật **SmartSpend Pro** trên Local Server bằng Docker Compose và PostgreSQL 18 cô lập, tuân thủ hoàn toàn kiến trúc `SERVER_CONTEXT.md` (`source/`, `data/`, `.env`, `docker-compose.yml` và `_proxy/sites/`).

---

## 1. Kiến trúc chuẩn trên Local Server

```text
~/apps/ (hoặc /srv/apps/)
├── _proxy/
│   └── sites/                      # Chép từ source/deploy/local-server/sites/
└── SmartSpendAI/
    ├── source/                     # Mã nguồn ứng dụng (đồng bộ từ PC)
    ├── .env                        # Biến môi trường production (chmod 600)
    ├── data/
    │   ├── postgres/               # Dữ liệu PostgreSQL 18 bền vững ngoài container
    │   └── backups/                # Các bản sao lưu pg_dump tự động
    └── docker-compose.yml          # Chép từ source/deploy/local-server/docker-compose.yml
```

| Hạng mục | Giá trị |
| --- | --- |
| Web container | Python 3.13, FastAPI, `read_only: true`, `cap_drop: ALL`, giới hạn 768 MiB RAM / 1.5 CPU |
| Cổng nội bộ | `127.0.0.1:8092` → `web:8000` (chỉ lắng nghe loopback cho Reverse Proxy / Tunnel) |
| Database | PostgreSQL 18 trên mạng nội bộ `internal: true` (cô lập Internet, không mở cổng 5432 ra host) |
| Dữ liệu bền vững | `./data/postgres` (Database) & `./data/backups` (Sao lưu tự động) |

---

## 2. Cập nhật lên Server đã có sẵn dự án (Không mất dữ liệu)

Nếu `SmartSpendAI` **đã có sẵn và đang chạy trên Local Server**, bạn chỉ cần chạy **1 lệnh duy nhất** từ PowerShell trên máy tính Windows tại thư mục dự án:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "<ssh-alias-hoac-user@ip>" -RemoteAppDir "~/apps/SmartSpendAI"
```

> **Mẹo nâng cấp bố cục:** Nếu trên server trước đây bạn giải nén dạng phẳng (`~/apps/SmartSpendAI/compose.yaml` dùng Docker volume) và muốn tự động chuyển sang đúng cấu trúc `source/` + `data/` của `SERVER_CONTEXT.md` mà giữ nguyên 100% dữ liệu, chỉ cần thêm cờ `-MigrateLayout`:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "<ssh-alias>" -RemoteAppDir "~/apps/SmartSpendAI" -MigrateLayout
> ```

### Hoặc cập nhật thủ công bằng `rsync` / `scp` + `update.sh`

```bash
# Từ máy tính đồng bộ mã nguồn vào thư mục source/ (không đụng tới .env và data/)
rsync -avz --delete \
  --exclude node_modules --exclude .git --exclude .env --exclude '.env.*' \
  --exclude config.json --exclude '*.db' --exclude output --exclude __pycache__ \
  ./ <ssh-alias>:~/apps/SmartSpendAI/source/

# Trên Server chạy trình cập nhật tự động (tự backup DB -> build -> migrate -> kiểm tra /healthz -> tự rollback nếu lỗi)
ssh <ssh-alias> "bash ~/apps/SmartSpendAI/source/scripts/homeserver/update.sh"
```

---

## 3. Cấu hình Reverse Proxy / Cloudflare Tunnel (`_proxy/sites/`)

Trong thư mục `deploy/local-server/sites/` đã chuẩn bị sẵn cấu hình mẫu cho cả 3 phương án phổ biến (tăng `read_timeout` lên `120s` để hỗ trợ các lượt gọi Gemini AI tạo thực đơn tuần):

- **Nginx:** Chép `deploy/local-server/sites/smartspend.nginx.conf` vào `_proxy/sites/smartspend.conf`, đổi `server_name` rồi chạy `nginx -t && systemctl reload nginx` (hoặc reload container proxy).
- **Caddy:** Chép nội dung `deploy/local-server/sites/smartspend.Caddyfile` vào Caddyfile / `_proxy/sites/` rồi reload Caddy.
- **Cloudflare Tunnel (`cloudflared`):** Trỏ hostname HTTPS về `http://127.0.0.1:8092` như mẫu `deploy/local-server/sites/smartspend.cloudflared.yml`.

Đảm bảo trong file `~/apps/SmartSpendAI/.env` có:

```dotenv
SMARTSPEND_PUBLIC_URL='https://smartspend.tenmiencuaban.com'
SMARTSPEND_TRUST_PROXY='1'
# Tùy chọn nếu muốn mở thêm bằng IP LAN hoặc Tailscale bên cạnh domain chính:
# SMARTSPEND_ALLOWED_HOSTS='192.168.1.50:8092,smartspend.tailnet.ts.net'
```

---

## 4. Cài mới lần đầu (Nếu dựng trên máy chủ trắng)

```bash
mkdir -p ~/apps/SmartSpendAI/{source,data/postgres,data/backups}
chmod 700 ~/apps/SmartSpendAI/data ~/apps/SmartSpendAI/data/postgres ~/apps/SmartSpendAI/data/backups
cd ~/apps/SmartSpendAI
tar -xzf ~/SmartSpendAI-hp.tar.gz -C ./source
cp ./source/deploy/local-server/docker-compose.yml ./docker-compose.yml
cp -n ./source/.env.example ./.env
chmod 600 ./.env
docker compose build web
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/setup" web python scripts/homeserver/configure.py --path /setup/.env
docker compose up -d --wait db
docker compose --profile tools run --rm migrate
docker compose up -d --wait web
curl --fail http://127.0.0.1:8092/healthz
```

---

## 5. Lịch sao lưu tự động hằng đêm

Script `backup.sh` tự động lưu vào `./data/backups/` (khi chạy theo bố cục `SERVER_CONTEXT.md`), không lộ `.env` dạng rõ và giữ tối đa 14 bản gần nhất:

```cron
30 3 * * * /bin/bash $HOME/apps/SmartSpendAI/source/scripts/homeserver/backup.sh >> $HOME/apps/SmartSpendAI/data/backups/backup.log 2>&1
```
