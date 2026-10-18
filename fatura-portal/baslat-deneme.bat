@echo off
rem Sahte GIB ile deneme: gercek fatura kesilmez. SMS kodu 123456.
cd /d "%~dp0"
set GIB_MOCK=1
start "" http://127.0.0.1:3000
node server.js
pause
