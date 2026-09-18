@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Fatura Cekme
echo ============================================
echo.
set "bas="
set "bit="
set "firma="
set /p bas="Baslangic tarihi (ornek 01/08/2026): "
set /p bit="Bitis tarihi     (ornek 31/08/2026): "
echo.
echo Tek firma ile denemek isterseniz firma adini yazin.
echo TUM firmalar icin bos birakip ENTER'a basin.
set /p firma="Firma adi: "
echo.
if "%firma%"=="" (
  python luca_bot.py --baslangic "%bas%" --bitis "%bit%"
) else (
  python luca_bot.py --baslangic "%bas%" --bitis "%bit%" --firma "%firma%"
)
echo.
pause
