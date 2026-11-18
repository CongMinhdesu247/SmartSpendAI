# SERVER_CONTEXT.md — Hồ sơ Local Server & Quy trình Cập nhật SmartSpendAI

> Hồ sơ cấu hình chuẩn hóa để cập nhật **SmartSpend Pro (`SmartSpendAI`)** lên Local Server của bạn theo đúng kiến trúc `_proxy/` + `<project>/{source, .env, data, docker-compose.yml}`, bảo toàn **100% dữ liệu và `.env` hiện có**.

---

## 1. Thông tin hệ thống & Kết nối SSH

- **Hệ điều hành (OS):** Linux `x86_64 (amd64)` (Ubuntu / Debian + Docker Compose v2)
- **SSH Alias / Địa chỉ kết nối:** `<ssh-alias>` *(ví dụ `my-server` hoặc `congminh@100.95.33.63` qua LAN / Tailscale)*
- **Khóa SSH tự động nhận diện (nếu có):** `$env:USERPROFILE\.ssh\homeserver_ed25519` (hoặc cấu hình trong `~/.ssh/config`)
- **Đường dẫn dự án trên Server:** `~/apps/SmartSpendAI` *(ví dụ `/home/congminh/apps/SmartSpendAI` hoặc `/srv/apps/SmartSpendAI`)*

---

## 2. Cấu trúc thư mục chuẩn trên Local Server

```text
<APPS_ROOT>/                        # Ví dụ: /home/<user>/apps/ hoặc /srv/apps/
├── _proxy/                         # Reverse Proxy / Cloudflare Tunnel dùng chung
│   ├── docker-compose.yml
│   └── sites/                      # Cấu hình route cho từng ứng dụng (mẫu tại deploy/local-server/sites/)
│       ├── smartspend.nginx.conf
│       ├── smartspend.Caddyfile
│       └── smartspend.cloudflared.yml
└── SmartSpendAI/                   # Thư mục độc lập của dự án SmartSpendAI
    ├── source/                     # Mã nguồn đồng bộ từ PC lên (KHÔNG chứa .env hay DB)
    ├── .env                        # Biến môi trường production riêng tư (chmod 600)
    ├── data/                       # Dữ liệu bền vững (Persistent) nằm ngoài container
    │   ├── postgres/               # Dữ liệu PostgreSQL 18 (mount vào /var/lib/postgresql)
    │   └── backups/                # Bản sao lưu pg_dump tự động trước mỗi lần update & hằng đêm
    └── docker-compose.yml          # File khởi chạy riêng của dự án (restart: unless-stopped)
```

> **Tương thích hoàn toàn với bản đã cài sẵn trên Server:**  
> Script `deploy_update.ps1` và `update.sh` tự động phát hiện dự án đang chạy trên server ở **cả 2 dạng**:
> 1. Đã theo bố cục `SmartSpendAI/{source, data, .env, docker-compose.yml}` → Giải nén code mới vào `source/` và cập nhật tại chỗ.
> 2. Đang ở bố cục phẳng `SmartSpendAI/{compose.yaml, .env}` → Cập nhật trực tiếp không gián đoạn, hoặc thêm cờ `-MigrateLayout` nếu bạn muốn tự động chuyển sang chuẩn `source/` + `data/` mà giữ nguyên 100% database!

---

## 3. Phân bổ Port, Mạng Cô lập & Biến môi trường `.env`

| Dự án | Loại | Port nội bộ (Host) | Tên Compose Project | Mạng Docker | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `_proxy` | Reverse Proxy / Tunnel | `80 / 443` | Proxy chung | Host / Proxy network | Đang chạy |
| `SmartSpendAI` | FastAPI + PostgreSQL 18 | `127.0.0.1:8092` | `smartspend-hp` | `smartspend_db_internal` (`internal: true`) + `smartspend_edge` | Cập nhật không mất dữ liệu |

### Các biến môi trường trong `<APPS_ROOT>/SmartSpendAI/.env`

*(Khi cập nhật lên server đã có sẵn dự án, bạn **giữ nguyên** file `.env` hiện tại; `update.sh` sẽ tự bổ sung `SMARTSPEND_TRUST_PROXY='1'` và `SMARTSPEND_TRUSTED_HEADER='auto'` nếu chưa có).*

```dotenv
SMARTSPEND_COMPOSE_PROJECT='smartspend-hp'
SMARTSPEND_HTTP_PORT='8092'
SMARTSPEND_IMAGE_TAG='local'
SMARTSPEND_DB_PASSWORD='<giu-nguyen-secret-hien-co>'
SMARTSPEND_DB_ADMIN_PASSWORD='<giu-nguyen-secret-hien-co>'
SMARTSPEND_PASSWORD_HASH='<giu-nguyen-argon2id-hash-hien-co>'
SMARTSPEND_SESSION_SECRET='<giu-nguyen-session-secret-hien-co>'
SMARTSPEND_ALLOW_REGISTRATION='0'
SMARTSPEND_INVITE_CODE=''
SMARTSPEND_PUBLIC_URL='https://smartspend.tenmiencuaban.com'
SMARTSPEND_ALLOWED_HOSTS=''
SMARTSPEND_TRUST_PROXY='1'
SMARTSPEND_TRUSTED_HEADER='auto'
GEMINI_API_KEY='<gemini-api-key-cua-ban>'
GEMINI_MODEL=''
```

---

## 4. Lệnh Cập nhật Bản Mới từ PC lên Local Server (1 Lệnh Duy Nhất)

### Bước 1 (Tùy chọn) — Kiểm tra nhanh trạng thái dự án hiện có trên Server

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "<ssh-alias-hoac-user@ip>" -RemoteAppDir "~/apps/SmartSpendAI" -CheckOnly
```

### Bước 2 — Đẩy bản nâng cấp lên Local Server (Tự động Backup DB → Build → Migrate → Healthcheck)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "<ssh-alias-hoac-user@ip>" -RemoteAppDir "~/apps/SmartSpendAI"
```

*(Nếu trên server đang là bố cục phẳng cũ và bạn muốn đồng thời chuẩn hóa sang `source/` + `data/` của `SERVER_CONTEXT.md`, thêm `-MigrateLayout` vào cuối lệnh trên).*

### Hoặc dùng `rsync` + `ssh` trên Linux / WSL / Git Bash

```bash
rsync -avz --delete \
  --exclude node_modules --exclude .git --exclude .env --exclude '.env.*' \
  --exclude config.json --exclude '*.db*' --exclude dist --exclude build \
  --exclude output --exclude __pycache__ \
  ./ <ssh-alias>:~/apps/SmartSpendAI/source/

ssh <ssh-alias> "bash ~/apps/SmartSpendAI/source/scripts/homeserver/update.sh"
```

---

## 5. Cấu hình Reverse Proxy / Cloudflare Tunnel (`_proxy/sites/`)

- **Nginx:** Xem mẫu [`deploy/local-server/sites/smartspend.nginx.conf`](deploy/local-server/sites/smartspend.nginx.conf) (`proxy_pass http://127.0.0.1:8092;`, `proxy_read_timeout 120s;`, chống giả mạo `CF-Connecting-IP`).
- **Caddy:** Xem mẫu [`deploy/local-server/sites/smartspend.Caddyfile`](deploy/local-server/sites/smartspend.Caddyfile) (`reverse_proxy 127.0.0.1:8092`).
- **Cloudflare Tunnel (`cloudflared`):** Xem mẫu [`deploy/local-server/sites/smartspend.cloudflared.yml`](deploy/local-server/sites/smartspend.cloudflared.yml) (`service: http://127.0.0.1:8092`).
