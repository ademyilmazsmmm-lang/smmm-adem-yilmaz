@echo off
set PYTHONUTF8=1
cd /d "%~dp0"

if not "%OPENAI_API_KEY%"=="" goto calistir

echo.
echo OpenAI API anahtarinizi yapistirin ve Enter'a basin.
echo Bir kez sorulur, bilgisayarda kayitli kalir.
set /p OPENAI_API_KEY=Anahtar: 
if "%OPENAI_API_KEY%"=="" goto anahtar_yok
setx OPENAI_API_KEY "%OPENAI_API_KEY%" >nul
goto calistir

:anahtar_yok
echo.
echo Anahtar girilmedi, cikiliyor.
pause
exit /b 1

:calistir
where python >nul 2>nul
if errorlevel 1 goto py_baslat
python fis_okuyucu.py
goto bitti

:py_baslat
py fis_okuyucu.py

:bitti
if errorlevel 2 goto gecersiz_anahtar
if errorlevel 1 goto hata
exit /b 0

:gecersiz_anahtar
setx OPENAI_API_KEY "" >nul
echo.
echo Kayitli anahtar gecersizdi ve silindi.
echo Bu pencereyi kapatip dosyaya tekrar cift tiklayin, YENI anahtari yapistirin.
pause
exit /b 2

:hata
echo.
echo Bir hata olustu. Yukaridaki mesaji kontrol edin.
pause
exit /b 1
