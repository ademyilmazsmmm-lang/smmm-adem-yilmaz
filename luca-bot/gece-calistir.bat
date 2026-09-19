@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Gece Calistirma (TUM FIRMALAR)
echo ============================================
echo.
echo Girisi siz yapacaksiniz, sonrasinda bilgisayari birakip gidebilirsiniz.
echo Is bitince tarayici kendiliginden kapanir.
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

set "bas="
set "bit="
set /p bas="Baslangic tarihi (ornek 01/08/2026): "
set /p bit="Bitis tarihi     (ornek 19/09/2026): "
echo.

%PY% luca_bot.py --baslangic "%bas%" --bitis "%bit%" --bitince-kapat
echo.
echo Is bitti. Sonuclar indirilenler klasorunde.
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
