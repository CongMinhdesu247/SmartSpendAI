@echo off
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 exit /b 1
title SmartSpend Pro - AI Cloud Finance & Planner
echo ===============================================================
echo   DANG KHOI DONG SMARTSPEND PRO...
echo ===============================================================
python -m launchers.desktop
pause
