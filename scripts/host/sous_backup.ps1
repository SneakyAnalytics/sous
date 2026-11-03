# Copies Sous's data to the external drive. Runs on the Beelink (Task Scheduler: SousBackup, daily) and by hand.
#
#   1. Takes a fresh, integrity-checked database snapshot inside the container.
#   2. Copies the snapshots and the recipe photos to <Dest>\db and <Dest>\images, then checks every copy by size.
#   3. Reports the result back into the app (so the Recipes page shows "backed up 3h ago", or a warning).
#
# It only ever ADDS files under <Dest>: nothing already on the drive is touched, and a photo deleted in the app stays
# in the backup. Old database snapshots are pruned (keeps the newest 10, and anything under 60 days old).
param(
    [string]$Dest = "D:\SousBackups",
    [string]$Container = "sous-api"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root "backup-staging"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "backup.log"
function Log($m) { Add-Content $log ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $m); Write-Output $m }

# Run a native command and fail loudly if it returns non-zero (PowerShell doesn't do this on its own).
function Run([string]$what, [scriptblock]$cmd) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"   # PS 5.1 turns native stderr into errors otherwise
    try { $out = & $cmd 2>&1 } finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE): $out" }
    return $out
}

function Report([bool]$ok, [string]$message, [hashtable]$extra = @{}) {
    $status = @{ ok = $ok; at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); message = $message; dest = $Dest } + $extra
    try {
        New-Item -ItemType Directory -Force $stage | Out-Null
        $file = Join-Path $stage "offsite_status.json"
        ($status | ConvertTo-Json -Compress) | Set-Content -Encoding ascii $file
        docker cp $file "${Container}:/app/data/offsite_status.json" 2>&1 | Out-Null
    } catch { Log "could not report status to the app: $_" }
}

try {
    $drive = Split-Path $Dest -Qualifier
    if (-not (Test-Path "$drive\")) { throw "backup drive $drive is not connected" }
    $running = Run "docker inspect" { docker inspect -f "{{.State.Running}}" $Container }
    if ("$running".Trim() -ne "true") { throw "container $Container is not running" }

    Run "database snapshot" { docker exec $Container python -c "from app import backup; print(backup.backup_now())" } | Out-Null

    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force "$stage\db", "$stage\images" | Out-Null
    Run "copy snapshots out of the container" { docker cp "${Container}:/app/data/backups/." "$stage\db" } | Out-Null
    docker exec $Container sh -c "test -d /app/data/images" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Run "copy photos out of the container" { docker cp "${Container}:/app/data/images/." "$stage\images" } | Out-Null
    }

    New-Item -ItemType Directory -Force "$Dest\db", "$Dest\images" | Out-Null
    # /FFT: FAT drives keep 2-second timestamps; /XO: don't recopy what is already there; never /MIR or /PURGE.
    robocopy "$stage\db" "$Dest\db" *.db /XO /FFT /R:2 /W:2 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy of snapshots failed (exit $LASTEXITCODE)" }
    robocopy "$stage\images" "$Dest\images" /E /XO /FFT /R:2 /W:2 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy of photos failed (exit $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0

    # Verify: every file we staged exists on the drive with the same size.
    $bad = @()
    foreach ($sub in "db", "images") {
        Get-ChildItem "$stage\$sub" -File -Recurse | ForEach-Object {
            $copy = Join-Path "$Dest\$sub" $_.Name
            if (-not (Test-Path $copy) -or (Get-Item $copy).Length -ne $_.Length) { $bad += $_.Name }
        }
    }
    if ($bad.Count) { throw "copies on the drive don't match for: $($bad -join ', ')" }

    # Prune old snapshots on the drive: keep the newest 10 and anything under 60 days old.
    Get-ChildItem "$Dest\db\recipes_*.db" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 10 |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force

    $dbs = @(Get-ChildItem "$Dest\db\recipes_*.db")
    $imgs = @(Get-ChildItem "$Dest\images" -File -ErrorAction SilentlyContinue)
    $freeGb = [math]::Round((Get-PSDrive ($drive.TrimEnd(":"))).Free / 1GB)
    $msg = "ok: $($dbs.Count) database snapshots, $($imgs.Count) photos, ${freeGb} GB free"
    Log $msg
    Report $true $msg @{ db_files = $dbs.Count; images = $imgs.Count; free_gb = $freeGb }
    if ($freeGb -lt 5) { Log "WARNING: only $freeGb GB free on $drive" }
    exit 0
} catch {
    Log "FAILED: $_"
    Report $false "$_"
    exit 1
}
