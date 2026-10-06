@echo off
chcp 65001 >nul
rem Python kurulu degilse: ne yapilacagini soyler, indirme sayfasini ve adim adim rehberi acar.
echo.
echo ==================================================
echo   Python bu bilgisayarda kurulu degil
echo ==================================================
echo.
echo   1) Acilan sayfadan Python'u indirip kurun.
echo      ONEMLI: kurulumun ilk ekraninda en alttaki
echo      "Add python.exe to PATH" kutusunu ISARETLEYIN,
echo      sonra "Install Now" deyin.
echo   2) Kurulum bitince bu pencereyi kapatin ve ayni dosyaya
echo      (luca-arayuz.bat) tekrar cift tiklayin.
echo.
echo   Adim adim anlatim ve sorun giderme: OKU-BENI-ONCE.txt
echo   (simdi acilacak).
echo.
start "" "https://www.python.org/downloads/windows/"
if exist "%~dp0OKU-BENI-ONCE.txt" start "" notepad "%~dp0OKU-BENI-ONCE.txt"
pause
exit /b 1
