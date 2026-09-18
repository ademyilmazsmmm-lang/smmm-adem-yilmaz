@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Kurulum (sadece bir kez)
echo ============================================
echo.
echo Python aranıyor...

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

echo Bulunan Python:
%PY% --version
echo.

echo Gerekli paketler kuruluyor...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto hata

echo.
echo Tarayıcı indiriliyor (birkaç dakika sürebilir)...
%PY% -m playwright install chromium
if errorlevel 1 goto hata

echo.
echo ============================================
echo   Kurulum tamamlandı.
echo   Sırada: firmalari-listele.bat
echo ============================================
pause
exit /b 0

:pythonyok
echo.
echo HATA: Python bulunamadı.
echo.
echo Komut istemine su komutu yazip deneyin:
echo     py install
echo.
echo Yine olmazsa python.org/downloads adresinden
echo klasik "Windows installer (64-bit)" dosyasini kurun
echo ve kurulumda "Add python.exe to PATH" kutusunu isaretleyin.
pause
exit /b 1

:hata
echo.
echo Kurulum sırasında hata oluştu. Bu ekranın görüntüsünü gönderin.
pause
exit /b 1
