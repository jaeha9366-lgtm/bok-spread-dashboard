@echo off
cd /d C:\Users\jaeha\Desktop\foi
echo [%date% %time%] Starting dashboard update... >> update_log.txt
.venv\Scripts\python.exe spread.py >> update_log.txt 2>&1
if %errorlevel% equ 0 (
    echo [%date% %time%] Dashboard update finished successfully. >> update_log.txt
) else (
    echo [%date% %time%] Dashboard update failed with exit code %errorlevel%. >> update_log.txt
)
