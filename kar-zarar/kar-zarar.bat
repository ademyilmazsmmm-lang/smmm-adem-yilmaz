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
  if exist ayarlar.ornek.json (
    copy /y ayarlar.ornek.json ayarlar.json >nul
    echo ayarlar.json yoktu, ornek dosyadan olusturuldu. Notepad aciliyor:
    echo uye_no, kullanici_adi, parola ^(varsa dogrulama_anahtari^) alanlarini doldurup KAYDEDIN, sonra kapatin.
    echo ^(Eski klasorunuzde ayarlar.json varsa onu bu klasore kopyalamak daha kolaydir.^)
    notepad ayarlar.json
  ) else (
    echo ayarlar.json ve ayarlar.ornek.json yok. Eski klasordeki ayarlar.json dosyasini buraya kopyalayin.
    pause
    exit /b 1
  )
)

set "aralik="
set "firma="
:tarihsor
set "aralik="
set /p aralik="Tarih araligi (ornek 01/07/2026-31/08/2026): "
if "%aralik%"=="" (
  echo Tarih araligi girmelisiniz.
  goto tarihsor
)
echo.
echo Belirli firmalar icin adlarinin bir kismini yazin (virgulle ayirin), TUM firmalar icin ENTER.
set /p firma="Firma adi: "
echo.
echo NOT: Defter Beyan giris sayfasi acilinca GUVENLIK KODUNU tarayicida siz yazip GIRIS YAP'a basin.
echo.
set TARIH=--tarih "%aralik%"
if "%firma%"=="" (
  %PY% kar_zarar.py %TARIH%
) else (
  %PY% kar_zarar.py %TARIH% --firma "%firma%"
)
echo.
pause
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. python.org'dan Python kurup tekrar deneyin (adim adim: ..\luca-bot\OKU-BENI-ONCE.txt).
pause
exit /b 1

:pakethata
echo HATA: Paketler kurulamadi. Bu ekranin goruntusunu gonderin.
pause
exit /b 1
