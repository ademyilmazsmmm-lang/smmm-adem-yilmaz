@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Arayuz
echo ============================================
echo.
echo Pencere aciliyor... (bu siyah pencere kucultulmus olarak arkada kalir,
echo kapatmayin; arayuzu kapatinca o da kapanir)
echo.

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto pakethata

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto tkyok

start "Luca Bot" /min %PY% luca_arayuz.py
exit /b 0

:pythonyok
echo HATA: Python bulunamadi. Once kurulum.bat dosyasini calistirin.
pause
exit /b 1

:pakethata
echo.
echo HATA: Kurulum tamamlanamadi. Bu ekranin goruntusunu gonderin.
pause
exit /b 1

:tkyok
echo HATA: Python'da pencere kutuphanesi (tkinter) yok.
echo python.org'dan Python'u indirip kurarken "tcl/tk and IDLE" secenegi
echo isaretli olsun (varsayilan olarak isaretlidir). Diger .bat dosyalari
echo bu olmadan da calismaya devam eder.
pause
exit /b 1
