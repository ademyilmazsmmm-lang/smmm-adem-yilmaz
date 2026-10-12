@echo off
chcp 65001 >nul
rem Python kurulu degilse: onay ister, python.org'dan indirip kullanici klasorune sessiz kurar (yonetici izni
rem gerekmez), sonra cagiran dosyayi (1. arguman) yeniden baslatir. Olmazsa elle kurulum yolunu gosterir.
echo.
echo ==================================================
echo   Python bu bilgisayarda kurulu degil
echo ==================================================
echo.
echo   Program Python ile calisir. Simdi OTOMATIK kurulabilir:
echo   internetten indirilir (yaklasik 25 MB), yonetici izni gerekmez,
echo   2-3 dakika surer. Kurulum bitince program kendiliginden acilir.
echo.
choice /c EH /n /m "  Simdi kurulsun mu?  [E] Evet   [H] Hayir, elle kuracagim: "
if errorlevel 2 goto elle

set "PYSURUM=3.12.10"
set "PYURL=https://www.python.org/ftp/python/%PYSURUM%/python-%PYSURUM%-amd64.exe"
set "PYEXE=%TEMP%\python-%PYSURUM%-amd64.exe"
echo.
echo   [1/3] Python indiriliyor...
if exist "%PYEXE%" del "%PYEXE%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%PYURL%' -OutFile '%PYEXE%'"
if not exist "%PYEXE%" goto indirilemedi
echo   [2/3] Indirilen dosya dogrulaniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-AuthenticodeSignature '%PYEXE%'; if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -like '*Python Software Foundation*'){exit 0}else{exit 1}"
if errorlevel 1 goto imzasiz
echo   [3/3] Python kuruluyor, 1-2 dakika surer. Pencereyi kapatmayin...
start "" /wait "%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_tcltk=1 Include_pip=1 Shortcuts=0
del "%PYEXE%" >nul 2>&1

set "PYKLASOR="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~D\python.exe" set "PYKLASOR=%%~D"
if not defined PYKLASOR goto kurulamadi
"%PYKLASOR%\python.exe" -c "import tkinter" >nul 2>&1
if errorlevel 1 goto kurulamadi
echo.
echo   Python kuruldu.
if "%~1"=="" goto elleac
if not exist "%~1" goto elleac
echo   Program aciliyor...
start "" "%~1"
exit /b 0

:elleac
echo   Simdi programi tekrar acin (luca-arayuz.bat dosyasina cift tiklayin).
pause
exit /b 0

:indirilemedi
echo.
echo   Python indirilemedi (internet baglantisi, guvenlik duvari ya da vekil sunucu olabilir).
goto elle

:imzasiz
echo.
echo   Indirilen dosyanin imzasi dogrulanamadi; guvenlik icin kurulmadi.
del "%PYEXE%" >nul 2>&1
goto elle

:kurulamadi
echo.
echo   Otomatik kurulum tamamlanamadi.
goto elle

:elle
echo.
echo ==================================================
echo   ELLE KURULUM - kisa yol
echo ==================================================
echo   1) Su baglanti Python'u DOGRUDAN indirir (simdi acilacak):
echo      https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
echo   2) Inen dosyaya cift tiklayin. ILK EKRANDA en alttaki
echo      "Add python.exe to PATH" kutusunu ISARETLEYIN, sonra "Install Now".
echo   3) Bitince programi tekrar acin.
echo.
echo   Ayrintili anlatim ve sorun giderme: OKU-BENI-ONCE.txt (simdi acilacak).
start "" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
if exist "%~dp0OKU-BENI-ONCE.txt" start "" notepad "%~dp0OKU-BENI-ONCE.txt"
pause
exit /b 1
