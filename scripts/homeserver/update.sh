#!/bin/bash
# =====================================================================
# SmartSpend Pro — Zero-Data-Loss Local Server Updater
# Hỗ trợ tự động cả 2 bố cục trên Server đã cài sẵn:
#   1. Chuẩn SERVER_CONTEXT.md: <APP_DIR>/{source, data, .env, docker-compose.yml}
#   2. Bố cục phẳng hiện có:    <APP_DIR>/{compose.yaml, .env, ...}
# Tùy chọn: --migrate-to-server-layout (chuyển bố cục phẳng sang source/ + data/ giữ 100% DB)
# =====================================================================
set -euo pipefail
umask 077

read_env_var() {
  local file="$1" key="$2" default_val="$3"
  if [ -f "$file" ]; then
    local val
    val=$(grep -E "^${key}=" "$file" | tail -n 1 | cut -d'=' -f2- | sed "s/^'//;s/'$//;s/^\"//;s/\"$//" || true)
    if [ -n "$val" ]; then
      echo "$val"
      return
    fi
  fi
  echo "$default_val"
}

ensure_env_default() {
  local file="$1" key="$2" value="$3"
  if [ -f "$file" ] && ! grep -qE "^${key}=" "$file"; then
    printf "%s='%s'\n" "$key" "$value" >> "$file"
    chmod 600 "$file"
  fi
}

main() {
  local migrate_layout=0
  for arg in "$@"; do
    if [ "$arg" = "--migrate-to-server-layout" ]; then
      migrate_layout=1
    fi
  done

  local script_dir source_root parent_dir app_dir compose_file env_file
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  source_root="$(cd "$script_dir/../.." && pwd)"
  parent_dir="$(dirname "$source_root")"

  # Optional one-time layout upgrade from flat <APP_DIR>/compose.yaml -> SERVER_CONTEXT.md structure
  if [ "$migrate_layout" = "1" ] && [ "$(basename "$source_root")" != "source" ] && [ -f "$source_root/compose.yaml" ]; then
    app_dir="$source_root"
    if [ -d "$app_dir/data/postgres" ] && [ -n "$(ls -A "$app_dir/data/postgres" 2>/dev/null || true)" ]; then
      echo "LỖI: $app_dir/data/postgres đã có dữ liệu. Dừng chuyển đổi tự động để bảo vệ dữ liệu." >&2
      exit 1
    fi
    echo "==> [Layout Upgrade] Sao lưu PostgreSQL hiện tại trước khi chuyển sang chuẩn SERVER_CONTEXT.md..."
    local dump_tmp="$app_dir/.migration-pre-layout.dump"
    docker compose -f "$app_dir/compose.yaml" up -d --wait db
    docker compose -f "$app_dir/compose.yaml" exec -T db pg_dump -U postgres -d smartspend -Fc --no-owner > "$dump_tmp"
    test -s "$dump_tmp"
    docker compose -f "$app_dir/compose.yaml" exec -T db pg_restore --list < "$dump_tmp" > /dev/null
    docker compose -f "$app_dir/compose.yaml" down

    mkdir -p "$app_dir/source" "$app_dir/data/postgres" "$app_dir/data/backups"
    chmod 700 "$app_dir/data" "$app_dir/data/postgres" "$app_dir/data/backups"

    shopt -s dotglob nullglob
    for item in "$app_dir"/*; do
      local base
      base="$(basename "$item")"
      case "$base" in
        .|..|source|data|.env|.migration-pre-layout.dump) continue ;;
      esac
      mv "$item" "$app_dir/source/"
    done
    shopt -u dotglob nullglob

    cp "$app_dir/source/deploy/local-server/docker-compose.yml" "$app_dir/docker-compose.yml"
    ensure_env_default "$app_dir/.env" "SMARTSPEND_TRUST_PROXY" "1"
    ensure_env_default "$app_dir/.env" "SMARTSPEND_COMPOSE_PROJECT" "smartspend-hp"

    cd "$app_dir"
    docker compose -f "$app_dir/docker-compose.yml" up -d --wait db
    if ! docker compose -f "$app_dir/docker-compose.yml" exec -T db pg_restore -U postgres -d smartspend --role=smartspend --no-owner --exit-on-error < "$dump_tmp"; then
      echo "CẢNH BÁO: Khôi phục sang ./data/postgres gặp sự cố. Đang hoàn trả bố cục cũ..." >&2
      docker compose -f "$app_dir/docker-compose.yml" down || true
      rm -rf "$app_dir/docker-compose.yml" "$app_dir/data/postgres"
      shopt -s dotglob nullglob
      for moved in "$app_dir/source"/*; do
        mv "$moved" "$app_dir/"
      done
      shopt -u dotglob nullglob
      rmdir "$app_dir/source" 2>/dev/null || true
      docker compose -f "$app_dir/compose.yaml" up -d --wait db web
      exit 1
    fi
    mv "$dump_tmp" "$app_dir/data/backups/migrated-from-flat-layout.dump"
    source_root="$app_dir/source"
    parent_dir="$app_dir"
    echo "==> [Layout Upgrade] Đã chuyển sang cấu trúc source/ + data/postgres an toàn 100%!"
  fi

  if [ "$(basename "$source_root")" = "source" ]; then
    app_dir="$parent_dir"
    compose_file="$app_dir/docker-compose.yml"
    env_file="$app_dir/.env"
    mkdir -p "$app_dir/data/postgres" "$app_dir/data/backups"
    chmod 700 "$app_dir/data" "$app_dir/data/postgres" "$app_dir/data/backups" 2>/dev/null || true
    if [ ! -f "$compose_file" ] && [ -f "$source_root/deploy/local-server/docker-compose.yml" ]; then
      cp "$source_root/deploy/local-server/docker-compose.yml" "$compose_file"
    fi
  else
    app_dir="$source_root"
    compose_file="$app_dir/compose.yaml"
    env_file="$app_dir/.env"
  fi

  if [ ! -f "$env_file" ]; then
    echo "LỖI: Không tìm thấy $env_file. Hãy kiểm tra đường dẫn thư mục dự án trên Server." >&2
    exit 1
  fi

  ensure_env_default "$env_file" "SMARTSPEND_TRUST_PROXY" "1"
  ensure_env_default "$env_file" "SMARTSPEND_TRUSTED_HEADER" "auto"

  local http_port image_tag image_name has_rollback=0
  http_port="$(read_env_var "$env_file" "SMARTSPEND_HTTP_PORT" "8092")"
  image_tag="$(read_env_var "$env_file" "SMARTSPEND_IMAGE_TAG" "local")"
  image_name="smartspend-hp-app:${image_tag}"

  cd "$app_dir"
  echo "==> [1/6] Đảm bảo PostgreSQL đang hoạt động trước khi sao lưu..."
  docker compose -f "$compose_file" up -d --wait db

  echo "==> [2/6] Tạo bản sao lưu cơ sở dữ liệu dự phòng..."
  bash "$source_root/scripts/homeserver/backup.sh"

  if docker image inspect "$image_name" > /dev/null 2>&1; then
    docker image tag "$image_name" "smartspend-hp-app:rollback"
    has_rollback=1
  fi

  echo "==> [3/6] Đóng gói Docker image mới cho SmartSpend Pro..."
  docker compose -f "$compose_file" build web

  echo "==> [4/6] Áp dụng migration & kiểm tra phân quyền Row-Level Security..."
  docker compose -f "$compose_file" --profile tools run --rm migrate
  docker compose -f "$compose_file" run --rm --no-deps web python scripts/homeserver/check_database.py

  echo "==> [5/6] Khởi động lại container web..."
  if ! docker compose -f "$compose_file" up -d --no-deps --wait web; then
    if [ "$has_rollback" = "1" ]; then
      echo "CẢNH BÁO: Khởi động web mới thất bại, đang tự động khôi phục bản :rollback..." >&2
      docker image tag "smartspend-hp-app:rollback" "$image_name"
      docker compose -f "$compose_file" up -d --no-deps --wait web
    fi
    exit 1
  fi

  echo "==> [6/6] Kiểm tra readiness HTTP /healthz tại 127.0.0.1:${http_port}..."
  if ! curl --fail --silent --show-error "http://127.0.0.1:${http_port}/healthz" > /dev/null; then
    if [ "$has_rollback" = "1" ]; then
      echo "CẢNH BÁO: /healthz báo lỗi, đang tự động khôi phục bản :rollback..." >&2
      docker image tag "smartspend-hp-app:rollback" "$image_name"
      docker compose -f "$compose_file" up -d --no-deps --wait web
    fi
    exit 1
  fi

  echo "====================================================================="
  echo "  CẬP NHẬT SMARTSPEND PRO LÊN LOCAL SERVER THÀNH CÔNG!"
  echo "  - Healthcheck: http://127.0.0.1:${http_port}/healthz (OK)"
  echo "  - Bố cục:      $([ "$(basename "$source_root")" = "source" ] && echo "SERVER_CONTEXT.md (source/ + data/)" || echo "Compose trực tiếp")"
  echo "  - Toàn bộ dữ liệu PostgreSQL & .env được giữ nguyên vẹn."
  echo "====================================================================="
}

main "$@"
