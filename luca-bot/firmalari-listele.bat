@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Luca'daki firma listesi okunacak. Tarayici acilinca giris yapin.
echo.
python luca_bot.py --listele
echo.
pause
