import subprocess

cmd = ["powershell", "-NoProfile", "-Command", "Get-Process chrome | Where-Object { $_.MainWindowTitle } | Select-Object Id, MainWindowTitle"]
res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
