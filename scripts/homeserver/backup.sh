#!/bin/bash
set -euo pipefail
umask 077

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
parent_dir="$(dirname "$source_root")"

# Auto-detect SERVER_CONTEXT.md layout (<project>/source + <project>/docker-compose.yml + <project>/data)
if [ "$(basename "$source_root")" = "source" ] && [ -f "$parent_dir/docker-compose.yml" ]; then
  compose_dir="$parent_dir"
  default_backup_dir="$parent_dir/data/backups"
  compose_file="$parent_dir/docker-compose.yml"
  env_file="${SMARTSPEND_ENV_FILE:-$parent_dir/.env}"
else
  compose_dir="$source_root"
  default_backup_dir="$HOME/backups/smartspend"
  compose_file="$source_root/compose.yaml"
  env_file="${SMARTSPEND_ENV_FILE:-$source_root/.env}"
fi

cd "$compose_dir"
backup_root="${SMARTSPEND_BACKUP_DIR:-$default_backup_dir}"
mkdir -p "$backup_root/auto"
exec 9>"$backup_root/.backup.lock"
flock -n 9 || { echo 'Another SmartSpend backup is running.' >&2; exit 1; }

stamp=$(date -u +%Y%m%dT%H%M%S%NZ)
destination="$backup_root/auto/$stamp"
mkdir "$destination"

docker compose -f "$compose_file" exec -T db pg_dump -U postgres -d smartspend -Fc --no-owner > "$destination/database.dump"
test -s "$destination/database.dump"
docker compose -f "$compose_file" exec -T db pg_restore --list < "$destination/database.dump" > /dev/null

# Keep .env only when explicitly requested or when GPG passphrase file is supplied.
if [ "${SMARTSPEND_INCLUDE_ENV_IN_EXPORT:-0}" = "1" ] && [ -f "$env_file" ]; then
  cp "$env_file" "$destination/.env"
fi
cp "$compose_file" "$source_root/Dockerfile.hp" "$source_root/requirements/homeserver.lock.txt" "$destination/"
cp -r "$source_root/scripts/homeserver" "$destination/scripts"
docker compose -f "$compose_file" images -q web > "$destination/web-image-id.txt"
touch "$destination/COMPLETE"

if [ -n "${SMARTSPEND_BACKUP_PASSPHRASE_FILE:-}" ]; then
  tar -czf - -C "$backup_root/auto" "$stamp" | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase-file "$SMARTSPEND_BACKUP_PASSPHRASE_FILE" -o "$backup_root/smartspend-export.tar.gz.gpg.tmp"
  mv "$backup_root/smartspend-export.tar.gz.gpg.tmp" "$backup_root/smartspend-export.tar.gz.gpg"
else
  tar -czf "$backup_root/smartspend-export.tar.gz.tmp" -C "$backup_root/auto" "$stamp"
  mv "$backup_root/smartspend-export.tar.gz.tmp" "$backup_root/smartspend-export.tar.gz"
fi

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
