<#
.SYNOPSIS
  Đóng gói và cập nhật SmartSpend Pro từ máy Windows lên Local Server đã cài sẵn qua SSH (0% mất dữ liệu).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "my-server" -RemoteAppDir "~/apps/SmartSpendAI"

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "congminh@100.95.33.63" -RemoteAppDir "/home/congminh/apps/SmartSpendAI"

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\homeserver\deploy_update.ps1 -SshTarget "my-server" -CheckOnly
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,

    [string]$RemoteAppDir = "~/apps/SmartSpendAI",

    [string]$SshKey = "",

    [switch]$MigrateLayout,

    [switch]$SyncCompose,

    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ProjectRoot

$SshArgs = @()
$ScpArgs = @()
if ($SshKey -eq "") {
    $DefaultHpKey = Join-Path $env:USERPROFILE ".ssh\homeserver_ed25519"
    if (Test-Path $DefaultHpKey) {
        $SshKey = $DefaultHpKey
    }
}
if ($SshKey -ne "") {
    $SshArgs += @("-i", $SshKey)
    $ScpArgs += @("-i", $SshKey)
}

if ($CheckOnly) {
    Write-Host "==> [Kiểm tra trạng thái] Đang đọc trạng thái SmartSpendAI trên $SshTarget..." -ForegroundColor Cyan
    $CheckScript = @"
set -euo pipefail
APP_DIR=$RemoteAppDir
echo "Thư mục dự án: `$APP_DIR"
if [ -d "`$APP_DIR/source" ]; then
  echo "Bố cục hiện tại: Chuẩn SERVER_CONTEXT.md (source/ + data/)"
elif [ -f "`$APP_DIR/compose.yaml" ]; then
  echo "Bố cục hiện tại: Phẳng (compose.yaml + named volume)"
else
  echo "Bố cục hiện tại: Chưa khởi tạo tại `$APP_DIR"
fi
docker ps --filter "name=smartspend" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
"@ -replace "`r`n", "`n"
    & ssh @SshArgs $SshTarget $CheckScript
    exit $LASTEXITCODE
}

Write-Host "==> [1/3] Đóng gói mã nguồn sạch (loại trừ .env, config.json, *.db*)..." -ForegroundColor Cyan
python scripts/homeserver/package.py
if ($LASTEXITCODE -ne 0) {
    throw "Đóng gói mã nguồn thất bại."
}

$ArchivePath = Join-Path $ProjectRoot "output\deployment\SmartSpendAI-hp.tar.gz"
if (-not (Test-Path $ArchivePath)) {
    throw "Không tìm thấy gói triển khai tại $ArchivePath"
}

Write-Host "==> [2/3] Tải gói cập nhật lên Local Server ($SshTarget)..." -ForegroundColor Cyan
& scp @ScpArgs $ArchivePath "${SshTarget}:~/SmartSpendAI-hp.tar.gz"
if ($LASTEXITCODE -ne 0) {
    throw "Không thể truyền file qua SCP lên $SshTarget."
}

$MigrateFlag = if ($MigrateLayout) { "--migrate-to-server-layout" } else { "" }
$ForceCompose = if ($SyncCompose) { "1" } else { "0" }
$RemoteScript = @"
set -euo pipefail
APP_DIR=$RemoteAppDir
FORCE_COMPOSE=$ForceCompose
if [ ! -d "`$APP_DIR" ]; then
  echo "LỖI: Không tìm thấy thư mục dự án `$APP_DIR trên Server. Hãy kiểm tra lại -RemoteAppDir." >&2
  rm -f ~/SmartSpendAI-hp.tar.gz
  exit 1
fi
if [ -d "`$APP_DIR/source" ]; then
  mkdir -p "`$APP_DIR/data/postgres" "`$APP_DIR/data/backups"
  tar -xzf ~/SmartSpendAI-hp.tar.gz -C "`$APP_DIR/source"
  if [ ! -f "`$APP_DIR/docker-compose.yml" ] || [ "`$FORCE_COMPOSE" = "1" ]; then
    cp "`$APP_DIR/source/deploy/local-server/docker-compose.yml" "`$APP_DIR/docker-compose.yml"
  fi
  rm -f ~/SmartSpendAI-hp.tar.gz
  bash "`$APP_DIR/source/scripts/homeserver/update.sh"
elif [ -f "`$APP_DIR/compose.yaml" ]; then
  tar -xzf ~/SmartSpendAI-hp.tar.gz -C "`$APP_DIR"
  rm -f ~/SmartSpendAI-hp.tar.gz
  bash "`$APP_DIR/scripts/homeserver/update.sh" $MigrateFlag
else
  echo "LỖI: Thư mục `$APP_DIR chưa có source/ hoặc compose.yaml." >&2
  rm -f ~/SmartSpendAI-hp.tar.gz
  exit 1
fi
"@ -replace "`r`n", "`n"

Write-Host "==> [3/3] Thực thi cập nhật, sao lưu DB, migrate & kiểm tra /healthz trên Server..." -ForegroundColor Cyan
& ssh @SshArgs $SshTarget $RemoteScript
if ($LASTEXITCODE -ne 0) {
    throw "Quá trình cập nhật trên Local Server báo lỗi. Bản sao lưu DB đã được giữ an toàn; hãy xem log phía trên."
}

Write-Host "==> Hoàn tất cập nhật SmartSpend Pro lên Local Server!" -ForegroundColor Green
