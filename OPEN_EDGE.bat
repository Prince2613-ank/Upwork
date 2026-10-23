@echo off
echo Starting Microsoft Edge on Port 9223...
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9223 --user-data-dir="%USERPROFILE%\edge_upwork_profile" --no-first-run --no-default-browser-check "https://www.upwork.com"
echo Done! Please log in to Upwork in the Edge window.
pause
