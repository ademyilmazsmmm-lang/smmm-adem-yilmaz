@echo off
chcp 65001 >nul
cd /d "%~dp0"

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

%PY% -c "import playwright" >nul 2>&1
if not errorlevel 1 goto hazir

echo Gerekli paketler eksik, simdi kuruluyor...
echo (Ilk seferde birkac dakika surebilir)
echo.
%PY% -m pip install -r requirements.txt
%PY% -m playwright install chromium
%PY% -c "import playwright" >nul 2>&1
if errorlevel 1 goto pakethata
echo.

:hazir
echo Luca'daki firma listesi okunacak. Tarayici acilinca giris yapin.
echo.
%PY% luca_bot.py --listele
echo.
pause
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. Once kurulum.bat dosyasini calistirin.
pause
exit /b 1

:pakethata
echo.
echo HATA: Paketler kurulamadi. Bu ekranin goruntusunu gonderin.
pause
exit /b 1
