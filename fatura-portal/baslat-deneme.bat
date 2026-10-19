@echo off
cd /d "%~dp0"
rem Eski program 3000 numarali kapiyi tutuyorsa once kapat
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
set GIB_MOCK=1
start "" http://127.0.0.1:3000
node server.js
pause
