@echo off
title Flodata 3-Chrome Launcher
cls
echo ============================================================
echo   FLODATA MULTI-CHROME LAUNCHER (3x SPEED MODE)
echo ============================================================
echo.

set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_EXE% set CHROME_EXE="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_EXE% (
    echo [ERROR] Chrome executable not found in Program Files!
    pause
    exit /b 1
)

echo [1/3] Starting Chrome 1 on port 9222 (Primary)...
start "" %CHROME_EXE% --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome_upwork_profile" "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"

ping 127.0.0.1 -n 3 >nul

echo [2/3] Starting Chrome 2 on port 9223...
if not exist "%USERPROFILE%\chrome_upwork_profile_2" mkdir "%USERPROFILE%\chrome_upwork_profile_2"
start "" %CHROME_EXE% --remote-debugging-port=9223 --user-data-dir="%USERPROFILE%\chrome_upwork_profile_2" "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"

ping 127.0.0.1 -n 3 >nul

echo [3/3] Starting Chrome 3 on port 9224...
if not exist "%USERPROFILE%\chrome_upwork_profile_3" mkdir "%USERPROFILE%\chrome_upwork_profile_3"
start "" %CHROME_EXE% --remote-debugging-port=9224 --user-data-dir="%USERPROFILE%\chrome_upwork_profile_3" "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"

echo.
echo ============================================================
echo   SUCCESS: 3 Chrome Windows Launched!
echo ============================================================
echo   Chrome 1 (port 9222) - Primary (already logged in)
echo   Chrome 2 (port 9223) - LOG IN to your Upwork account
echo   Chrome 3 (port 9224) - LOG IN to your Upwork account
echo ============================================================
echo.
echo Once logged into all 3, open terminal and run:
echo   python run_parallel.py
echo.
pause
