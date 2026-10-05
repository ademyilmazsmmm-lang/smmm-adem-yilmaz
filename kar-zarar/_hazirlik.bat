@echo off
rem Python paketlerini kontrol eder, eksikse kurar (_python-bul.bat once cagrilmali).
%PY% -c "import playwright, openpyxl, pyotp" >nul 2>&1
if not errorlevel 1 exit /b 0
echo Gerekli paketler kuruluyor...
%PY% -m pip install -r requirements.txt
%PY% -c "import playwright" >nul 2>&1
if errorlevel 1 exit /b 1
echo Hazir.
exit /b 0
