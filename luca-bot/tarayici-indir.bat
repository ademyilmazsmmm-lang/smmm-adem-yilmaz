@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Playwright tarayicisini indir
echo ============================================
echo.
echo Bu dosya SADECE bilgisayarinizda Chrome ve Edge yoksa gereklidir.
echo Normalde bot kurulu Chrome'u kullanir, indirme yapmaz.
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

%PY% -m playwright install chromium
if errorlevel 1 goto hata
echo.
echo Indirme tamamlandi.
pause
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. Once kurulum.bat dosyasini calistirin.
pause
exit /b 1

:hata
echo.
echo Indirme basarisiz (internet baglantisi engelleniyor olabilir).
echo En kolay cozum: google.com/chrome adresinden Chrome kurun.
pause
exit /b 1
