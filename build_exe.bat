@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 exit /b 1
title Build SmartSpend Pro Desktop (.exe)
echo ===============================================================
echo   DANG DONG GOI SMARTSPEND PRO THANH FILE .EXE DOC LAP...
echo ===============================================================
python -c "import PyInstaller, fastapi, uvicorn, sqlalchemy, psycopg2, google.genai, webview, pwdlib, qrcode" >nul 2>&1
if errorlevel 1 (
  echo Loi: Chua du thu vien. Chay: python -m pip install -r requirements.txt
  goto :failed
)
python -m PyInstaller --noconfirm --onefile --windowed --clean ^
  --name "SmartSpendPro" ^
  --add-data "frontend;frontend" ^
  --hidden-import "sqlalchemy.dialects.postgresql" ^
  --hidden-import "sqlalchemy.dialects.sqlite" ^
  --hidden-import "psycopg2" ^
  desktop_launcher.py
if errorlevel 1 goto :failed
if not exist "dist\SmartSpendPro.exe" goto :failed

echo.
echo ===============================================================
echo   HOAN TAT! File chay nam tai: dist\SmartSpendPro.exe
echo ===============================================================
if /I not "%~1"=="--no-pause" pause
exit /b 0

:failed
echo DONG GOI THAT BAI. Hay xem thong bao loi phia tren.
if /I not "%~1"=="--no-pause" pause
exit /b 1
