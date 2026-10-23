import subprocess

cmd = """Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" | ForEach-Object { $_.CommandLine }"""
out = subprocess.check_output(["powershell", "-NoProfile", "-Command", cmd], text=True)
for line in out.splitlines():
    if "--remote-debugging-port" in line:
        print("FOUND:", line)
