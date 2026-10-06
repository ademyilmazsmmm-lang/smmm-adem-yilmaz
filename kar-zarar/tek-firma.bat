@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Kar / Zarar - TEK FIRMA DENEMESI
echo ============================================
echo   Tum musterileri gezmez; yalniz yazdiginiz firmayi okur ve her adimdan
echo   sonra ekran goruntusu kaydeder.
echo     1 = Luca Mizan / hesap plani (1.Sinif / bilanco firmalari)
echo     2 = Defter Beyan       (isletme defteri firmalari; guvenlik kodunu siz yazarsiniz)
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
set "kaynak=1"
set /p kaynak="Kaynak 1=Luca, 2=Defter Beyan (ENTER = 1): "
if "%kaynak%"=="" set "kaynak=1"
:tarihsor
set "aralik="
set /p aralik="Tarih araligi (ornek 01/07/2026-31/08/2026): "
if "%aralik%"=="" (
  echo Tarih araligi girmelisiniz.
  goto tarihsor
)
set TARIH=--tarih "%aralik%"
set /p firma="Firma adi (Luca listesindeki gibi, ornek DENTAL): "
if "%firma%"=="" (
  echo Firma adi yazmadiniz.
  pause
  exit /b 1
)
echo.
if "%kaynak%"=="2" (
  %PY% kar_zarar.py --sadece-defterbeyan %TARIH% --firma "%firma%"
) else (
  %PY% kar_zarar.py --sadece-luca %TARIH% --firma "%firma%"
)
echo.
echo Tani dosyalari: cikti\^<tarih^>\tani\mizan-*.png, hesap-plani-*.png veya defterbeyan-*.png ^(ve *.html^); indirilen Mizan: cikti\^<tarih^>\mizan
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
