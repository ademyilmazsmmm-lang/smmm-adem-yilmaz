@echo off
rem Paketleri ve tarayiciyi kontrol eder, eksik olani kurar.
rem Cagirmadan once _python-bul.bat ile PY degiskeni ayarlanmis olmali.

%PY% -c "import playwright" >nul 2>&1
if not errorlevel 1 goto tarayici

echo Gerekli paketler kuruluyor...
%PY% -m pip install -r requirements.txt
%PY% -c "import playwright" >nul 2>&1
if errorlevel 1 exit /b 1

:tarayici
echo Tarayici kontrol ediliyor (ilk seferde indirme birkac dakika surer)...
%PY% -m playwright install chromium
if errorlevel 1 exit /b 1
echo Hazir.
echo.
exit /b 0
