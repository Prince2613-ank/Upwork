@echo off
title Launch Microsoft Edge (Port 9223)
echo =====================================================
echo   Launching Microsoft Edge on Port 9223...
echo =====================================================

if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    cd /d "C:\Program Files (x86)\Microsoft\Edge\Application"
) else (
    cd /d "C:\Program Files\Microsoft\Edge\Application"
)

start msedge.exe --remote-debugging-port=9223 --user-data-dir="%USERPROFILE%\edge_upwork_profile" --no-first-run --no-default-browser-check --new-window "https://www.upwork.com"

echo.
echo Edge is now running on Port 9223!
ping 127.0.0.1 -n 3 >nul
