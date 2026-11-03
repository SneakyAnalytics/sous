# Registers (or updates) the daily SousBackup task on the Beelink. Safe to re-run; deploy_to_beelink.sh does.
# Interactive logon, like FitnessTrackerDockerWatchdog: the docker CLI works in the console session, and the Beelink auto-logs in.
param([string]$Time = "03:15")
$script = Join-Path $PSScriptRoot "sous_backup.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: if the Beelink was off at 03:15, back up when it's next up (unlike chores, a late backup is harmless).
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "SousBackup" -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Copies Sous recipes and photos to the external drive" -Force | Out-Null
"SousBackup registered (daily at $Time)"
