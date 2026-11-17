#!/bin/bash
set -euo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
backup_root="${SMARTSPEND_BACKUP_DIR:-/home/congminh/backups/smartspend}"
mkdir -p "$backup_root/auto"
exec 9>"$backup_root/.backup.lock"
flock -n 9 || { echo 'Another SmartSpend backup is running.' >&2; exit 1; }
stamp=$(date -u +%Y%m%dT%H%M%S%NZ)
destination="$backup_root/auto/$stamp"
mkdir "$destination"
docker compose exec -T db pg_dump -U postgres -d smartspend -Fc --no-owner > "$destination/database.dump"
test -s "$destination/database.dump"
docker compose exec -T db pg_restore --list < "$destination/database.dump" > /dev/null
cp "${SMARTSPEND_ENV_FILE:-.env}" "$destination/.env"
cp compose.yaml Dockerfile.hp requirements/homeserver.lock.txt "$destination/"
cp -r scripts/homeserver "$destination/scripts"
docker compose images -q web > "$destination/web-image-id.txt"
touch "$destination/COMPLETE"
tar -czf "$backup_root/smartspend-export.tar.gz.tmp" -C "$backup_root/auto" "$stamp"
mv "$backup_root/smartspend-export.tar.gz.tmp" "$backup_root/smartspend-export.tar.gz"
# Retention only after both the dump and export succeed; never remove incomplete backups.
python3 - "$backup_root/auto" <<'PY'
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
complete = sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and (p / 'COMPLETE').is_file())
for path in complete[:-14]:
    shutil.rmtree(path)
PY
echo "SmartSpend backup completed: $destination"
