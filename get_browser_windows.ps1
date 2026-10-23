Get-Process chrome, msedge -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, MainWindowTitle | Where-Object { $_.MainWindowTitle -ne "" } | Format-Table -AutoSize
