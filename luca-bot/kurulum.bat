@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Kurulum (sadece bir kez)
echo ============================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
  echo HATA: Python bulunamadi.
  echo python.org/downloads adresinden kurun ve kurulumda
  echo "Add python.exe to PATH" kutusunu isaretleyin.
  pause
  exit /b 1
)
echo Gerekli paketler kuruluyor...
python -m pip install -r requirements.txt
if errorlevel 1 goto hata
echo.
echo Tarayici indiriliyor (birkac dakika surebilir)...
python -m playwright install chromium
if errorlevel 1 goto hata
echo.
echo ============================================
echo   Kurulum tamamlandi. Artik calistir.bat
echo   dosyasini calistirabilirsiniz.
echo ============================================
pause
exit /b 0

:hata
echo.
echo Kurulum sirasinda hata olustu. Ekrani bana gonderin.
pause
exit /b 1
