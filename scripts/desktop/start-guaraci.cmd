@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-guaraci.ps1" %*
endlocal
