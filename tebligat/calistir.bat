@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Once kur.bat dosyasini bir kere calistirin.
  pause
  exit /b 1
)
.venv\Scripts\python.exe tebligat_tara.py %*
echo.
pause
