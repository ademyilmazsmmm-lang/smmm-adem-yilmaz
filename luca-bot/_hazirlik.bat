@echo off
rem Python paketlerini kontrol eder, eksikse kurar.
rem Tarayici olarak bilgisayardaki Chrome/Edge kullanilir, indirmeye gerek yoktur.
rem Cagirmadan once _python-bul.bat ile PY degiskeni ayarlanmis olmali.

%PY% -c "import playwright, openpyxl, pyotp" >nul 2>&1
if not errorlevel 1 exit /b 0

echo Gerekli paketler kuruluyor...
%PY% -m pip install -r requirements.txt
%PY% -c "import playwright" >nul 2>&1
if errorlevel 1 exit /b 1
rem openpyxl yoksa rapor sadece CSV olur, pyotp yoksa dogrulama kodu elle
rem girilir; ikisi de calismayi durdurmaz
echo Hazir.
echo.
exit /b 0
