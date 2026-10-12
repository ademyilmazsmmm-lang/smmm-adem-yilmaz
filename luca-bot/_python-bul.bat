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

rem Python.org yukleyicisi PATH'e eklenmemis ya da bu pencere kurulumdan once acilmis olabilir: kullanici klasorune bakilir.
set "PYKLASOR="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~D\python.exe" set "PYKLASOR=%%~D"
if not defined PYKLASOR goto pybul_devam
set "PATH=%PYKLASOR%;%PYKLASOR%\Scripts;%PATH%"
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY exit /b 0
:pybul_devam

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
