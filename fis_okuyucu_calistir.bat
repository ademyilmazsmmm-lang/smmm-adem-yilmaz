@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

if "%OPENAI_API_KEY%"=="" (
    echo.
    echo OpenAI API anahtarinizi yapistirin ve Enter'a basin.
    echo ^(Bir kez sorulur, bilgisayarda kayitli kalir.^)
    set /p OPENAI_API_KEY=Anahtar: 
    if "%OPENAI_API_KEY%"=="" (
        echo Anahtar girilmedi, cikiliyor.
        pause
        exit /b 1
    )
    setx OPENAI_API_KEY "%OPENAI_API_KEY%" >nul
)

where python >nul 2>nul
if %errorlevel%==0 (
    python fis_okuyucu.py
) else (
    py fis_okuyucu.py
)

if errorlevel 1 (
    echo.
    echo Bir hata olustu. Yukaridaki mesaji kontrol edin.
    pause
)
