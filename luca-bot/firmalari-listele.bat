@echo off
chcp 65001 >nul
cd /d "%~dp0"

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

echo Luca'daki firma listesi okunacak. Tarayici acilinca giris yapin.
echo.
%PY% luca_bot.py --listele
echo.
pause
exit /b 0

:pythonyok
call "%~dp0_python-yok.bat"
exit /b 1

:pakethata
echo.
echo HATA: Kurulum tamamlanamadi. Bu ekranin goruntusunu gonderin.
pause
exit /b 1
