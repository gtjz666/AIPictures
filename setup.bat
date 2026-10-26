@echo off
cd /d "%~dp0"
py -3.13 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
pause
