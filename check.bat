@echo off
title Bolo Dukaan - key check
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run start.bat once first, so it can set things up.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" check.py
pause
