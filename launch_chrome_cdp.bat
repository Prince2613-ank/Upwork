@echo off
REM ==============================================================================
REM Launch Google Chrome with Remote Debugging Port 9222 for Upwork Intelligence
REM ==============================================================================

echo [Flodata Analytics] Starting Google Chrome with Remote Debugging on port 9222...

set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_EXE% (
    set CHROME_EXE="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

if not exist %CHROME_EXE% (
    echo Error: Could not locate chrome.exe in Program Files.
    pause
    exit /b 1
)

set PROFILE_DIR="%USERPROFILE%\chrome_upwork_profile"
if not exist %PROFILE_DIR% mkdir %PROFILE_DIR%

start "" %CHROME_EXE% --remote-debugging-port=9222 --user-data-dir=%PROFILE_DIR% "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"

echo Chrome launched with --remote-debugging-port=9222 and dedicated profile.
echo Profile directory: %PROFILE_DIR%
echo.
echo IMPORTANT: If prompted, log into your Upwork account in this Chrome window.
echo Your login session will be saved permanently in this dedicated profile!
echo.
echo Once logged in, run:
echo   python main.py --test-3
echo   or
echo   python main.py --dashboard
