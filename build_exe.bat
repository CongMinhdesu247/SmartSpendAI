@echo off
chcp 65001 >nul
title Build SmartSpend Pro Desktop (.exe)
echo ===============================================================
echo   DANG DONG GOI SMARTSPEND PRO THANH FILE .EXE DOC LAP...
echo ===============================================================
pyinstaller --noconfirm --onefile --windowed --clean ^
  --name "SmartSpendPro" ^
  --add-data "frontend;frontend" ^
  --add-data "backend;backend" ^
  --hidden-import "sqlalchemy.dialects.postgresql" ^
  --hidden-import "sqlalchemy.dialects.sqlite" ^
  --hidden-import "psycopg2" ^
  desktop_launcher.py

echo.
echo ===============================================================
echo   HOAN TAT! File chay nam tai: dist\SmartSpendPro.exe
echo ===============================================================
pause
