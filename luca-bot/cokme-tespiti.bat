@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Cokme Tespiti
echo ============================================
echo.
echo Tarayicinin cokme sebebini kaydeder.
echo Cikti hem ekrana hem cokme-gunlugu.txt dosyasina yazilir.
echo Tek firma ile calistirin, cokmeyi gorunce dosyayi gonderin.
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

set "bas="
set "bit="
set "firma="
set /p bas="Baslangic tarihi (ornek 01/08/2026): "
set /p bit="Bitis tarihi     (ornek 31/08/2026): "
set /p firma="Firma adi (ornek GULAY): "
echo.

%PY% luca_bot.py --chrome-gunlugu --baslangic "%bas%" --bitis "%bit%" --firma "%firma%" > cokme-gunlugu.txt 2>&1
echo.
echo Bitti. cokme-gunlugu.txt dosyasini gonderin.
pause
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. Once kurulum.bat dosyasini calistirin.
pause
exit /b 1

:pakethata
echo HATA: Kurulum tamamlanamadi.
pause
exit /b 1
