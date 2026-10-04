@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Kar / Zarar Tahmini
echo ============================================
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok
call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

if not exist ayarlar.json (
  echo ayarlar.json yok. ayarlar.ornek.json dosyasini kopyalayip adini ayarlar.json yapin,
  echo Luca giris bilgilerinizi ^(uye_no, kullanici_adi, parola^) doldurun.
  pause
  exit /b 1
)

set "bas="
set "bit="
set "firma="
set /p bas="Baslangic tarihi (ornek 01/07/2026): "
set /p bit="Bitis tarihi     (ornek 31/08/2026): "
echo.
echo Belirli firmalar icin adlarinin bir kismini yazin (virgulle ayirin), TUM firmalar icin ENTER.
set /p firma="Firma adi: "
echo.
echo NOT: Defter Beyan giris sayfasi acilinca GUVENLIK KODUNU tarayicida siz yazip GIRIS YAP'a basin.
echo.
if "%firma%"=="" (
  %PY% kar_zarar.py --baslangic "%bas%" --bitis "%bit%"
) else (
  %PY% kar_zarar.py --baslangic "%bas%" --bitis "%bit%" --firma "%firma%"
)
echo.
pause
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. python.org'dan Python kurup tekrar deneyin.
pause
exit /b 1

:pakethata
echo HATA: Paketler kurulamadi. Bu ekranin goruntusunu gonderin.
pause
exit /b 1
