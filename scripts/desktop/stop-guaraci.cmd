@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-guaraci.ps1" %*
endlocal
