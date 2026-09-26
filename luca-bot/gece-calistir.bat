@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Gece Calistirma (TUM FIRMALAR)
echo ============================================
echo.
echo Giris ayarlar.json'daki bilgilerle otomatik yapilir; bilgisayari
echo birakip gidebilirsiniz. Is bitince tarayici kendiliginden kapanir.
echo.
echo Iki asamali dogrulama acikken kod istenirse bot giremez; calistirmadan
echo once tarayicidan bir kez elle girip oturumu acik birakin.
echo.
echo Butun ekranlar calisir (e-Arsiv, e-Fatura, GIB 5000/30000, TURMOB,
echo e-SMM ve Interaktif V.D.).
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

%PY% luca_bot.py --hepsi --baslangic "%bas%" --bitis "%bit%" --bitince-kapat
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
