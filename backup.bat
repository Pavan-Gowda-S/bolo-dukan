@echo off
setlocal
cd /d "%~dp0"
python scripts\backup.py %*
if errorlevel 1 pause
