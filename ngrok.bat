@echo off
title ngrok - Bolo Dukaan public link
where ngrok >nul 2>nul
if errorlevel 1 (
  echo.
  echo   ngrok is not installed. Install it with:
  echo       winget install ngrok.ngrok
  echo   then sign up at https://dashboard.ngrok.com and run:
  echo       ngrok config add-authtoken YOUR_TOKEN
  echo.
  pause
  exit /b 1
)
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"
echo.
echo   Starting ngrok for port %PORT%. Bolo Dukaan picks up the https link automatically.
echo   Keep this window open during the demo.
echo   (Server on another port? Run:  ngrok.bat 8001)
echo.
ngrok http %PORT%
