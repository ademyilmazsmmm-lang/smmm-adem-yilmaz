@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca'ya Tek Tikla Giris
echo ============================================
echo.
echo ayarlar.json'daki bilgilerle otomatik giris yapilir, Luca acilir ve
echo tarayici acik kalir - calismaniza devam edebilirsiniz.
echo (Bu, fatura cekme botundan ayri, sadece giris icin kucuk bir arac.)
echo.
echo Bu dosyayi hem ofis hem ev bilgisayarina kopyalayip (ya da OneDrive
echo ile paylasip) her ikisinde de kullanabilirsiniz.
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

%PY% luca_giris.py
if errorlevel 1 (
  pause
)
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. Once kurulum.bat dosyasini calistirin.
pause
exit /b 1

:pakethata
echo.
echo HATA: Kurulum tamamlanamadi. Bu ekranin goruntusunu gonderin.
pause
exit /b 1
