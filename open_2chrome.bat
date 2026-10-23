@echo off
echo =====================================================
echo   FLODATA - Opening Chrome on Port 9222 + 9223
echo =====================================================
echo.

REM Kill any existing Chrome on these ports first
echo Closing any existing Chrome instances on ports 9222/9223...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9222 "') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9223 "') do taskkill /PID %%a /F 2>nul
timeout /t 2 /nobreak >nul

echo.
echo Opening Chrome 1 on port 9222 (Profile: chrome_upwork_profile)...
start "Chrome-9222" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%USERPROFILE%\chrome_upwork_profile" ^
  --disable-fre --no-default-browser-check --no-first-run ^
  --new-window "https://www.upwork.com/login"

timeout /t 3 /nobreak >nul

echo Opening Chrome 2 on port 9223 (Profile: chrome_upwork_profile_2)...
start "Chrome-9223" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9223 ^
  --user-data-dir="%USERPROFILE%\chrome_upwork_profile_2" ^
  --disable-fre --no-default-browser-check --no-first-run ^
  --new-window "https://www.upwork.com/login"

echo.
echo =====================================================
echo  Both Chrome windows are now OPEN.
echo  
echo  1. Log into Upwork in BOTH windows
echo  2. Once logged in, run:  python fetch_14day_dual_chrome.py
echo =====================================================
echo.
pause
