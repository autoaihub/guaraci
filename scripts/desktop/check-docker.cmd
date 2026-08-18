@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-docker.ps1" %*
endlocal
