@echo off
rem Tebligat yardimcisi kurulumu. Bir kere calistirilir.
cd /d "%~dp0"

set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY (
  python --version >nul 2>nul && set PY=python
)
if not defined PY (
  echo Python bulunamadi. Microsoft Store'dan "Python 3.12" kurup bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)

echo Python bulundu: %PY%
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Sanal ortam olusturulamadi.
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Kurulum basarisiz oldu. Internet baglantisini kontrol edip tekrar deneyin.
  pause
  exit /b 1
)
echo.
echo Kurulum tamam. Simdi calistir.bat dosyasini calistirabilirsiniz.
pause
