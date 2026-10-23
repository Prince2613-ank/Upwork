import subprocess
import json

ps_cmd = 'Get-WmiObject Win32_Process | Where-Object { $_.Name -eq "chrome.exe" -and $_.CommandLine -notmatch "--type=" } | Select-Object ProcessId, CommandLine | ConvertTo-Json'
res = subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True, text=True)
try:
    data = json.loads(res.stdout)
    if isinstance(data, dict):
        data = [data]
    for d in data:
        print(f"PID: {d.get('ProcessId')}")
        print(f"Cmd: {d.get('CommandLine')}\n")
except Exception as e:
    print("Raw output:", res.stdout)
