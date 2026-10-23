@echo off
title Upwork Live Scraper Chrome Launcher
cls
echo ============================================================
echo   FLODATA: OPENING CHROME WINDOWS FOR LIVE UPWORK SCRAPING
echo ============================================================
echo.

set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_EXE% set CHROME_EXE="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

REM Clean any old stuck port processes
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9222 "') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9223 "') do taskkill /PID %%a /F 2>nul
timeout /t 1 /nobreak >nul

if not exist "%USERPROFILE%\chrome_upwork_profile" mkdir "%USERPROFILE%\chrome_upwork_profile"
if not exist "%USERPROFILE%\chrome_upwork_profile_2" mkdir "%USERPROFILE%\chrome_upwork_profile_2"

echo [1/2] Launching Chrome 1 (Port 9222)...
start "" %CHROME_EXE% --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome_upwork_profile" --no-first-run --no-default-browser-check --new-window "https://www.upwork.com/login"

timeout /t 2 /nobreak >nul

echo [2/2] Launching Chrome 2 (Port 9223)...
start "" %CHROME_EXE% --remote-debugging-port=9223 --user-data-dir="%USERPROFILE%\chrome_upwork_profile_2" --no-first-run --no-default-browser-check --new-window "https://www.upwork.com/login"

echo.
echo ============================================================
echo   BOTH CHROME WINDOWS ARE NOW OPEN ON YOUR SCREEN!
echo ============================================================
echo   1. Log into your Upwork account in BOTH windows.
echo   2. Leave both windows open so you can watch live scraping!
echo ============================================================
echo.
pause
