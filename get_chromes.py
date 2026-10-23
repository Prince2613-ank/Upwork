import subprocess

cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | Select-Object ProcessId, CommandLine"]
res = subprocess.run(cmd, capture_output=True, text=True)
for line in res.stdout.splitlines():
    if "remote-debugging-port" in line or "chrome_upwork_profile" in line:
        print(line[:120])
