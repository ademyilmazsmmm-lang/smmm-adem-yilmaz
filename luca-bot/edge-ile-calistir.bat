@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Edge ile Calistir
echo ============================================
echo.
echo Chrome indirme sirasinda cokuyorsa bunu kullanin.
echo Edge'de Luca'ya bir kez giris yapmaniz gerekir.
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
  %PY% luca_bot.py --tarayici edge --baslangic "%bas%" --bitis "%bit%"
) else (
  %PY% luca_bot.py --tarayici edge --baslangic "%bas%" --bitis "%bit%" --firma "%firma%"
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
