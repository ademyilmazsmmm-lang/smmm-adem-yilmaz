@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   SABAHKI SURUM - Karsilastirma Testi
echo ============================================
echo.
echo 35 firmayi sorunsuz ceken surumun aynisi.
echo Amac: cokme bu surumde de oluyor mu?
echo.
echo Bu surum Chrome kullanir ve kendi profilini olusturur,
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
set /p bit="Bitis tarihi     (ornek 31/08/2026): "
set /p firma="Firma adi (ornek AKIN): "
echo.

%PY% luca_bot_sabahki.py --baslangic "%bas%" --bitis "%bit%" --firma "%firma%"
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
