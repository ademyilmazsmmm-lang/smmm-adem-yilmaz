@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Bagimsiz Tarayici ile Calistir
echo ============================================
echo.
echo Playwright'in kendi Chromium'unu kullanir.
echo HP Sure Click / Kaspersky gibi programlar Chrome ve Edge'e baglanir;
echo bu tarayici onlarin disinda kaldigi icin cokme yasanmayabilir.
echo.
echo Ilk kullanimda tarayici-indir.bat calistirilmis olmali.
echo Luca'ya bir kez elle giris yapmaniz gerekir.
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

set "bas="
set "bit="
set "firma="
set /p bas="Baslangic tarihi (ornek 01/08/2026): "
set /p bit="Bitis tarihi     (ornek 19/09/2026): "
echo.
echo TUM firmalar icin bos birakip ENTER'a basin.
set /p firma="Firma adi: "
echo.
if "%firma%"=="" (
  %PY% luca_bot.py --tarayici chromium --baslangic "%bas%" --bitis "%bit%"
) else (
  %PY% luca_bot.py --tarayici chromium --baslangic "%bas%" --bitis "%bit%" --firma "%firma%"
)
echo.
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
