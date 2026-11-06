@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe exit /b 1
set "monitor_action=%~1"
if "%monitor_action%"=="" set "monitor_action=status"
.venv\Scripts\python.exe -m aipictures.gpu_watch %monitor_action% --data "%~dp0data"
if /i "%monitor_action%"=="status" pause
