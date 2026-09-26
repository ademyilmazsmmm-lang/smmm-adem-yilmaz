@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Eski Gunluk Raporlari Tek Rapora Birlestir
echo ============================================
echo.
echo Bu, BIR KEREYE MAHSUS calistirilacak bir gecis aracidir.
echo Eskiden her gun (indirilenler\2026-09-25\rapor.xlsx gibi) ayri bir
echo rapor olusuyordu; artik tek ve surekli bir rapor var
echo (indirilenler\rapor.xlsx). Bu arac gecmis gunlerin bilgilerini o tek
echo rapora isler; hicbir ekrani yeniden calistirmaya gerek kalmaz.
echo.
echo Eski gunluk rapor dosyalarina dokunulmaz. Mevcut surekli rapor varsa
echo uzerine yazmadan once yedeklenir.
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

%PY% gecis_rapor_birlestir.py
echo.
pause
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
