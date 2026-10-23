import subprocess, sys

cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chrome_upwork_profile_2*' } | Select-Object -ExpandProperty ProcessId"]
res = subprocess.run(cmd, capture_output=True, text=True)
pids = [p.strip() for p in res.stdout.splitlines() if p.strip()]
print("Profile 2 PIDs:", pids)

if pids:
    for pid in pids:
        print(f"Terminating lingering profile 2 PID: {pid}")
        subprocess.run(["taskkill", "/F", "/PID", pid])
