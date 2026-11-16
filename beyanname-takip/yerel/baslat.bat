@echo off
rem Siyah pencereli baslatma (hata ayiklama icin). Gunluk kullanim: "Beyanname Takip.vbs" (siyah pencere acmaz).
chcp 65001 >nul
cd /d "%~dp0"
if not exist ayarlar.env (
  echo ayarlar.env yok. ayarlar-ornek.env dosyasini kopyalayip adini ayarlar.env yapin ve doldurun.
  pause
  exit /b 1
)
call kur.bat
if errorlevel 1 exit /b 1
set BASLAT_BAT=1
.venv\Scripts\python.exe baslat.py
pause
