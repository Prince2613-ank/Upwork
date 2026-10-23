@echo off
echo Starting Chrome on Port 9222...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome_upwork_profile" --no-first-run "https://www.upwork.com"
echo Done! Please log in to Upwork in the Chrome window.
pause
