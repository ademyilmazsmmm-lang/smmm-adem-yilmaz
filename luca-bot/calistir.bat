@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Fatura Cekme
echo ============================================
echo.

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
echo Kurulum tamam, devam ediliyor.
echo.

:hazir
set "bas="
set "bit="
set "firma="
set /p bas="Baslangic tarihi (ornek 01/08/2026): "
set /p bit="Bitis tarihi     (ornek 31/08/2026): "
echo.
echo Tek firma ile denemek isterseniz firma adinin bir kismini yazin.
echo TUM firmalar icin bos birakip ENTER'a basin.
set /p firma="Firma adi: "
echo.
if "%firma%"=="" (
  %PY% luca_bot.py --baslangic "%bas%" --bitis "%bit%"
) else (
  %PY% luca_bot.py --baslangic "%bas%" --bitis "%bit%" --firma "%firma%"
)
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
