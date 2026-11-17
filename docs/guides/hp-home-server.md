# Đưa SmartSpendAI lên HP, từng bước

Các file đã được chuẩn bị trên PC. Chưa SSH vào HP, chưa xác minh cổng trống hay thay đổi hai website hiện có. Tài liệu hạ tầng ngày 15/11/2026 chỉ là tham khảo; trạng thái thật trên HP quyết định bước tiếp theo.

## 1. Cấu hình được chuẩn bị

| Hạng mục | Giá trị |
|---|---|
| Thư mục trên HP | `/home/congminh/apps/SmartSpendAI` |
| Compose project | `smartspend-hp` |
| Web | Python 3.13, FastAPI, giao diện tĩnh cùng origin, 1 worker |
| Cổng đề xuất | `127.0.0.1:8092` → web:8000; cần kiểm tra trống |
| Database | PostgreSQL 18 riêng; không publish 5432 |
| Volume | `smartspend-hp_postgres_data` |
| Ngân sách container | Web tối đa 768 MiB / 1,5 CPU; DB 512 MiB / 1 CPU |
| Backup riêng | `/home/congminh/backups/smartspend` |

Không cần Node, Python framework hoặc PostgreSQL trên host. Không cần Redis, Kafka hay Nginx. CPU/RAM trên là giới hạn thử ban đầu, không phải cam kết tải. Build cần RAM bổ sung; đo lại RAM khi cả ba web hoạt động. Image Python/Postgres khóa digest; thư viện Python khóa cả phụ thuộc gián tiếp trong `requirements/homeserver.lock.txt`. Khi cập nhật bảo mật cần chủ động nâng digest/lock và kiểm tra lại.

Ứng dụng dùng tài khoản DB `smartspend` không có SUPERUSER, BYPASSRLS, CREATEDB hoặc CREATEROLE. Đây là chủ schema theo thiết kế hiện tại, không phải tài khoản chỉ có quyền CRUD; dữ liệu sổ được truy cập qua role `smartspend_ledger` với RLS. Role `anon`/`authenticated` là role NOLOGIN phục vụ tương thích migration cũ, không kết nối Supabase.

**Dữ liệu:** quy trình này tạo database mới. Nó không tự đọc `.env.cloud`, không dùng DB BankingPrj, không chuyển SQLite/Supabase hiện có. Nếu muốn giữ dữ liệu cũ trên PC/cloud, đừng nhập dữ liệu thật vào DB mới trước khi có kế hoạch chuyển riêng và kiểm tra số bản ghi. Đổi URL desktop không chuyển dữ liệu. Backup BankingPrj hiện có không bao phủ SmartSpendAI.

## 2. Kiểm tra SSH và đóng gói trên PC Windows

Mở PowerShell tại thư mục dự án:

```powershell
cd C:\Users\ADMIN\Downloads\SmartSpendAI
Test-Path "$env:USERPROFILE\.ssh\homeserver_ed25519"
python scripts/homeserver/package.py
ssh -i "$env:USERPROFILE\.ssh\homeserver_ed25519" congminh@100.95.33.63
```

Kết quả mong đợi: tạo `output\deployment\SmartSpendAI-hp.tar.gz`, sau đó vào shell HP. Archive chỉ chứa source/cấu hình mẫu, không chứa `.env`, `.env.cloud`, database, API key từ config hoặc SSH key. Máy hiện tại dùng tài khoản ADMIN còn brief ghi khóa ở tài khoản Dung: nếu `Test-Path` trả False, dùng đúng đường dẫn khóa bạn đang quản lý; không tạo đè khóa, không gửi khóa/mật khẩu vào chat. PC và HP cần kết nối Tailscale. Lần SSH đầu hãy xác minh fingerprint HP qua kênh tin cậy.

## 3. Kiểm tra server trước khi chép/chạy

**Trên HP**, tại thư mục home sau SSH:

```bash
hostname
uname -m
free -h
df -h /
docker compose version
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
sudo ss -lntup
sudo ss -ltnp 'sport = :8092'
sudo ufw status verbose
systemctl --failed --no-pager
```

Mong đợi kiến trúc `x86_64`, Docker hoạt động, hai web hiện có vẫn bình thường, và truy vấn cổng 8092 chỉ có tiêu đề. **Nếu có tiến trình ở 8092: chọn cổng khác, kiểm tra cổng đó, rồi nhập cổng mới ở bước 5 và thay mọi `8092` bên dưới bằng cổng đó.** Đừng dừng dịch vụ đang chiếm cổng. Nếu RAM khả dụng thấp hoặc ổ gần đầy, xử lý trước; không chạy nhiều build cùng lúc.

Nếu Docker báo permission denied, cần dùng tài khoản đã được cấp quyền Docker hoặc nhờ quản trị cấu hình; không sửa quyền Docker socket thành 666.

```bash
mkdir -p /home/congminh/apps/SmartSpendAI
ls -la /home/congminh/apps/SmartSpendAI
```

Lần đầu thư mục cần trống. Nếu đã có bản SmartSpendAI thì chuyển sang mục cập nhật bên dưới, không giải nén đè vô điều kiện.

## 4. Chép archive từ PC sang HP

**Mở một PowerShell khác trên PC**, vẫn ở thư mục dự án:

```powershell
cd C:\Users\ADMIN\Downloads\SmartSpendAI
scp -i "$env:USERPROFILE\.ssh\homeserver_ed25519" .\output\deployment\SmartSpendAI-hp.tar.gz congminh@100.95.33.63:/home/congminh/SmartSpendAI-hp.tar.gz
```

**Quay lại shell HP:**

```bash
cd /home/congminh/apps/SmartSpendAI
tar -xzf /home/congminh/SmartSpendAI-hp.tar.gz
cp -n .env.example .env
chmod 600 .env
docker compose config --quiet
docker compose build web
```

Build thành công phải báo image `smartspend-hp-app:local` đã build. Chưa chạy web/database ở bước này. Dùng `config --quiet` để kiểm tra cú pháp; không chia sẻ output `docker compose config` đầy đủ vì nó chứa secret.

## 5. Tạo cấu hình riêng tư

**Trên HP, trong `/home/congminh/apps/SmartSpendAI`:**

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/setup" web python scripts/homeserver/configure.py --path /setup/.env
```

Công cụ hỏi cổng, địa chỉ HTTPS, mật khẩu mới của `chuso` hai lần và Gemini API key. Mật khẩu/key được nhập ẩn; DB password và session secret tự sinh, không hiện ra log. Bỏ trống key nếu muốn bổ sung sau (AI sẽ chưa hoạt động).

Nếu đã có hostname HTTPS hợp lệ, nhập hostname đó. Nếu chưa có domain/tunnel, nhập tạm `https://replace-me.example.com`; sau bước tunnel phải sửa thành URL thật trước khi đăng nhập. Không mặc định `020407.xyz` đã đăng ký thành công.

`.env` được lưu quyền 600. Argon2 hash chứa dấu `$` phải giữ trong **nháy đơn** như công cụ đã tạo. Không chạy công cụ lần nữa để đổi mật khẩu DB của volume đã có; thay `.env` không tự đổi password bên trong PostgreSQL. Đổi mật khẩu chủ sổ cũng không thực hiện bằng cách đổi hash trong `.env` sau migration.

## 6. Khởi tạo database, backup và migration

**Trên HP, cùng thư mục:** chạy từng lệnh và dừng nếu có lỗi.

```bash
docker compose config --quiet
docker compose up -d --wait db
bash scripts/homeserver/backup.sh
docker compose run --rm migrate
docker compose run --rm --no-deps web python scripts/homeserver/check_database.py
docker compose up -d --wait web
docker compose ps
curl --fail http://127.0.0.1:8092/healthz
```

Mong đợi: DB healthy; backup thành công; migration `status: applied`; kiểm tra DB `OK`; web healthy; HTTP trả `{"status":"ok"}`. Migration lần sau trả `already_applied` là bình thường. Profile `tools` chỉ chạy khi gọi `migrate`, không tự thay schema mỗi lần boot. Compose đợi DB healthy ở lúc khởi động; web dùng restart policy để thử khởi động lại nếu DB tạm chưa sẵn sàng.

Kiểm tra lỗi:

```bash
docker compose logs --tail=80 web
docker compose logs --tail=80 db
```

Không paste log chứa thông tin riêng tư vào chat. Web báo thiếu public URL/hash/secret: sửa `.env`. DB auth failed: kiểm tra liệu volume đã có từ lần cấu hình trước; không xóa volume hoặc tự sinh lại DB password. Nếu script init lỗi: xem log DB và sửa nguyên nhân trước, không coi `pg_isready` là bằng chứng đã tạo đủ schema. Migration phải thành công mới chạy web.

## 7. Tạo HTTPS cho web thứ ba

### Cách A: thử bằng Quick Tunnel khi chưa có domain

**Trên HP, cùng thư mục:** tạo tunnel mới, không dùng/sửa container tunnel của hai web khác:

```bash
docker run -d --name smartspend-hp-quick-tunnel --network host --restart unless-stopped --memory 128m --cpus 0.5 --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 cloudflare/cloudflared:2026.10.0 tunnel --no-autoupdate --url http://127.0.0.1:8092
docker logs --tail=80 smartspend-hp-quick-tunnel
```

Tìm URL `https://...trycloudflare.com`. Nếu tên container đã tồn tại, xem container/log trước, không chạy lại lệnh tạo. Image cloudflared này là tag phiên bản; có thể khóa thêm digest sau khi pull. Lần đầu nếu tag không tải được, kiểm tra kết nối/image chính thức trước; không thay bằng image của bên lạ.

```bash
nano .env
```

Sửa đúng một dòng, ví dụ `SMARTSPEND_PUBLIC_URL='https://URL-THAT.trycloudflare.com'`, lưu Ctrl+O, Enter rồi thoát Ctrl+X. Giữ nguyên các secret khác.

```bash
docker compose up -d --no-deps --force-recreate web
```

Không dùng `restart web` để nạp biến môi trường mới. Sau khi tiến trình tunnel chạy lại, Quick Tunnel có thể đổi URL: xem lại log, sửa public URL và recreate web. URL cũ trong bookmark/PWA cũng cần cập nhật. Đây là phương án thử; hostname cố định phù hợp hơn khi dùng hằng ngày.

### Cách B: hostname cố định nếu đã có domain hợp lệ

Trong Cloudflare quản lý tunnel cố định đang hoạt động, **thêm** published application route/hostname riêng cho SmartSpendAI, trỏ service tới `http://127.0.0.1:8092`. Giữ các route của hai web hiện có. Cách này giả định connector chạy trên host hoặc host network như brief; nếu connector nằm trong bridge network, `localhost` là container connector và cần kiểm tra topology trước.

Chỉ tạo DNS/route cho domain bạn đã xác minh sở hữu và đang Active. Không lấy tên miền Pending trong brief làm địa chỉ thật. Không đặt Origin Server HTTP Host Header thành `localhost`; app yêu cầu Host trùng hostname public. Đặt `SMARTSPEND_PUBLIC_URL` thành origin HTTPS đó rồi recreate web như cách A. Không cần mở cổng router/UFW.

### Kiểm tra trên iPhone qua 4G

Tắt Wi-Fi, mở URL HTTPS, đăng nhập tên **chuso** với mật khẩu đã đặt ở bước 5. Thử tạo khoản chi nhỏ, tải lại, kiểm tra vẫn còn; thử đăng xuất/đăng nhập. Thử tài khoản thứ hai để xác nhận sổ riêng. Nếu dùng AI, cấu hình key rồi thử một yêu cầu để kiểm tra quota/model thực tế.

Mở `https://HOSTNAME/healthz` phải trả JSON ok. Lỗi 502: kiểm tra tunnel, cổng và health nội bộ. Lỗi 400 “Địa chỉ truy cập không hợp lệ”: Host/public URL chưa khớp. Lỗi 403 khi ghi: kiểm tra origin và URL đang mở. Truy cập `http://IP-HP:8092` trực tiếp không phải đường sử dụng: port chỉ bind loopback và cookie đăng nhập yêu cầu HTTPS.

App hiện cho phép người biết URL đăng ký tài khoản mới; chưa có lời mời, khôi phục mật khẩu hay xác thực email. Các tài khoản dùng chung quota Gemini của chủ ứng dụng. Đây chưa phải xác nhận sẵn sàng nhận dữ liệu khách hàng.

## 8. Backup hằng ngày và kéo về PC

Backup dùng `pg_dump` nhất quán khi DB đang chạy; không sao chép trực tiếp thư mục DB. Gồm DB custom dump (schema/data và ACL, bỏ owner), `.env`, Compose, Dockerfile, lockfile, script vận hành và ID image web. Role được dựng lại bằng init, quyền bảng được giữ trong dump. Hiện ứng dụng không có kho upload phía server; nếu bổ sung upload phải thêm volume và backup tương ứng. Source/frontend nằm trong archive bàn giao; giữ thêm bản source theo mỗi release.

**HP:**

```bash
cd /home/congminh/apps/SmartSpendAI
bash scripts/homeserver/backup.sh
mkdir -p /home/congminh/backups/smartspend
chmod 700 /home/congminh/backups/smartspend
crontab -e
```

Thêm đúng một dòng vào crontab của **congminh**, không xóa các dòng đang có:

```cron
30 3 * * * cd /home/congminh/apps/SmartSpendAI && /bin/bash scripts/homeserver/backup.sh >> /home/congminh/backups/smartspend/backup.log 2>&1
```

03:30 theo timezone HP; kiểm tra bằng `timedatectl`, tránh trùng đợt build/backup nặng. Mỗi backup thành công tạo thư mục có marker COMPLETE, giữ 14 bản hoàn tất mới nhất sau khi export thành công. Bản chưa hoàn tất không tự xóa. Cron chưa được cài cho tới khi bạn thực hiện bước này. Log backup nhỏ nhưng tăng theo thời gian; thêm logrotate nếu vận hành lâu.

**PC PowerShell:**

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\SmartSpendBackup" | Out-Null
$backupFile = Join-Path "$env:USERPROFILE\Documents\SmartSpendBackup" ("smartspend-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.tar.gz')
scp -i "$env:USERPROFILE\.ssh\homeserver_ed25519" congminh@100.95.33.63:/home/congminh/backups/smartspend/smartspend-export.tar.gz $backupFile
```

Kéo sau lần backup thử và định kỳ; lịch tự tải BankingPrj không tự kéo SmartSpendAI. Các bản PC trong lệnh trên không tự dọn. Backup có dữ liệu tài chính và secret, chưa mã hóa bằng script này: bảo vệ tài khoản/ổ đĩa, giữ thêm bản mã hóa ở thiết bị ngoài HP và tốt nhất ngoài nhà.

## 9. Thử phục hồi vào đích riêng

**HP, thư mục dự án:** quy trình này chỉ dùng project **smartspend-restore**, tuyệt đối giữ `-p smartspend-restore` trong mọi lệnh của mục này. Đích phải là project restore mới/trống; nếu đã thử trước, dùng tên project mới nhất quán để tránh ghi đè bản thử cũ.

```bash
cd /home/congminh/apps/SmartSpendAI
docker compose -p smartspend-restore up -d --wait db
```

Chọn một đường dẫn backup có COMPLETE từ `ls /home/congminh/backups/smartspend/auto`. Thay `THOI_DIEM_BACKUP` ở dưới bằng tên thư mục thực tế:

```bash
docker compose -p smartspend-restore exec -T db pg_restore -U postgres -d smartspend --role=smartspend --no-owner --exit-on-error < /home/congminh/backups/smartspend/auto/THOI_DIEM_BACKUP/database.dump
docker compose -p smartspend-restore run --rm --no-deps migrate
docker compose -p smartspend-restore run --rm --no-deps web python scripts/homeserver/check_database.py
docker compose -p smartspend-restore down
```

Mong đợi restore mã thoát 0, migration nếu backup trước migration sẽ `applied`, nếu đã có schema sẽ `already_applied`. Kiểm tra số bản ghi và quyền truy cập phải OK. Không khởi động service web trong project restore nên không chiếm cổng của web thật. `down` giữ volume thử để đối chiếu.

**Lưu ý ACL:** giữ ACL để phục hồi chính xác RLS/GRANT; không thêm `--no-acl` vào lệnh dump/restore. Role cấp cluster không nằm trong dump database, nên phải chạy init DB trên volume mới trước như trên.

Đây là diễn tập DB. Khi HP hỏng, cần dựng lại source đúng release, `.env` tương ứng, các role bằng init DB rồi khôi phục dump như trên; kiểm tra đầy đủ ứng dụng và tunnel trước khi chuyển người dùng. Không restore đè DB đang nhận giao dịch. Không xóa marker migration để ép chạy lại. Dữ liệu phát sinh sau backup không có trong bản phục hồi.

## 10. Cập nhật và rollback

Trên PC đóng gói lại và chép archive như bước 2/4. Trên HP, cùng thư mục dự án:

```bash
bash scripts/homeserver/backup.sh
docker image tag smartspend-hp-app:local smartspend-hp-app:previous
tar -xzf /home/congminh/SmartSpendAI-hp.tar.gz
docker compose build web
docker compose stop web
docker compose run --rm migrate
docker compose up -d --no-deps --wait web
curl --fail http://127.0.0.1:8092/healthz
docker compose ps
```

Chạy từng lệnh; build hoặc migration lỗi thì dừng, đọc log. Chỉ thao tác trong thư mục SmartSpendAI. Archive không có `.env` nên giữ cấu hình riêng. Trước cập nhật nên giữ archive source cũ và archive backup ở PC; tag `previous` chỉ giữ một phiên bản gần nhất. Nếu đã đổi `SMARTSPEND_IMAGE_TAG` khỏi `local`, thay các lệnh tag cho khớp.

Rollback code khi **schema vẫn tương thích**:

```bash
SMARTSPEND_IMAGE_TAG=previous docker compose up -d --no-deps --force-recreate web
```

Sau rollback, đặt `SMARTSPEND_IMAGE_TAG='previous'` trong `.env` nếu cần giữ lựa chọn đó cho các lần vận hành tiếp theo. Nếu schema không tương thích, không chỉ quay lại image; phục hồi backup vào project riêng, kiểm tra rồi mới lên kế hoạch chuyển. Quy trình hiện tại không tự migration phá dữ liệu ngoài migration ledger có sẵn; bản cập nhật tương lai cần xem xét schema riêng.

Dừng riêng web: `docker compose stop web`; chạy lại: `docker compose up -d web`. Dừng stack SmartSpendAI giữ dữ liệu: `docker compose down`. Quick Tunnel tạo bằng `docker run` độc lập, muốn dừng dùng `docker stop smartspend-hp-quick-tunnel`. Không chạy `down -v`, `docker system prune --volumes` hoặc lệnh dọn toàn server.

## 11. Monitoring và kiểm tra sau reboot

Kiểm tra thủ công:

```bash
docker compose ps
docker stats --no-stream
curl --fail http://127.0.0.1:8092/healthz
find /home/congminh/backups/smartspend/auto -maxdepth 2 -name COMPLETE -mmin -1800 -print
```

Health HTTP hiện tại là liveness, không kiểm tra query DB mỗi lần. Dùng `check_database.py` ở bước 6 để kiểm tra DB thực tế. Docker không tự restart chỉ vì trạng thái unhealthy; restart policy xử lý tiến trình thoát, còn unhealthy cần điều tra log/tài nguyên.

Để thêm vào monitor Telegram hiện có, cần đọc cấu trúc `/usr/local/lib/hp-server-monitor/monitor.py` tại HP trước khi sửa: thêm web/DB project `smartspend-hp`, tunnel thực sự sử dụng, HTTP 8092 và tuổi backup/export <30 giờ. Không sửa file Telegram secret. Bộ bàn giao chưa tự tích hợp monitor đó vì chưa đọc cấu hình thật. Cần kiểm tra HTTPS từ thiết bị ngoài nhà và việc backup tới PC riêng.

Sau lần reboot bảo trì có kế hoạch, kiểm tra hai web cũ, `docker compose ps`, healthz và đăng nhập HTTPS. Nếu Quick Tunnel đổi URL, cập nhật bước 7. Chưa có số liệu tải trên HP: kiểm tra lại RAM khi ba web chạy, thời gian đáp ứng và yêu cầu AI trước khi tăng người dùng.

Tham khảo chính thức: [Compose và readiness](https://docs.docker.com/compose/how-tos/startup-order/), [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/), [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/).
