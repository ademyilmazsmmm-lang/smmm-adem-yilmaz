@echo off
rem Calisan Python komutunu bulur ve PY degiskenine yazar.
rem Yeni Python Install Manager'da "python" yalnizca bir kisayol; asil surum ayrica kuruluyor.
set "PY="

python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY exit /b 0

py -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY exit /b 0

where py >nul 2>&1
if errorlevel 1 exit /b 1

echo.
echo Python surumu kurulu degil. Simdi indiriliyor (birkac dakika surebilir)...
echo.
py install
py -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY exit /b 0
exit /b 1
