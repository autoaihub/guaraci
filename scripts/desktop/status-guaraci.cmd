@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0status-guaraci.ps1" %*
endlocal
