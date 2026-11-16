@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe exit /b 0
echo Ilk kurulum: Python ortami hazirlaniyor. 3-5 dakika surebilir; bu pencereyi kapatmayin.
py -3 -m venv .venv
if errorlevel 1 (
  echo Python bulunamadi. python.org adresinden Python 3.12 veya ustunu kurun ve kurulumda Add python.exe to PATH kutusunu isaretleyin.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r ..\requirements.txt playwright pyotp openpyxl pypdf
if errorlevel 1 (
  echo Kurulum basarisiz oldu. Yukaridaki hata yazisini gonderin.
  rmdir /s /q .venv
  pause
  exit /b 1
)
echo Kurulum tamam.
exit /b 0
