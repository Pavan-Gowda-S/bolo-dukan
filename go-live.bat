@echo off
title Bolo Dukaan - go live
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0go-live.ps1" %*
