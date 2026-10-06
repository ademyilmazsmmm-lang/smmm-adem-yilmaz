@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Luca Bot - Kurulum (sadece bir kez)
echo ============================================
echo.
echo Python araniyor...

call "%~dp0_python-bul.bat"
if errorlevel 1 goto pythonyok

echo Bulunan Python:
%PY% --version
echo.

call "%~dp0_hazirlik.bat"
if errorlevel 1 goto hata

echo ============================================
echo   Kurulum tamamlandi.
echo   Sirada: firmalari-listele.bat
echo ============================================
pause
exit /b 0

:pythonyok
call "%~dp0_python-yok.bat"
exit /b 1

:hata
echo.
echo Kurulum sirasinda hata olustu. Bu ekranin goruntusunu gonderin.
pause
exit /b 1
