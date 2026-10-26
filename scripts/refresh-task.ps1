<#
.SYNOPSIS
  Install / inspect / remove the Windows scheduled task that keeps the NBA database up to date.

.DESCRIPTION
  The task runs `python -m nbadash.ingest refresh` every N minutes (default 30) while you are logged on. Each run is
  quick when nothing happened: it looks at the NBA scoreboard and only refreshes when a game has finished that the
  database doesn't know about yet, or once a day as a catch-up. No console window opens (pythonw), output goes to
  backend\data\refresh.log.

  .\scripts\refresh-task.ps1 install [-Minutes 30]
  .\scripts\refresh-task.ps1 status
  .\scripts\refresh-task.ps1 run          # trigger a pass right now
  .\scripts\refresh-task.ps1 uninstall

  If scripts are blocked:  powershell -ExecutionPolicy Bypass -File .\scripts\refresh-task.ps1 status
#>
param(
    [Parameter(Position = 0)][ValidateSet('install', 'uninstall', 'status', 'run')][string]$Action = 'status',
    [int]$Minutes = 30,
    [string]$PythonPath = ''   # override if the right interpreter isn't found automatically
)

$ErrorActionPreference = 'Stop'
$TaskName = 'NBA Dashboard Refresh'
$Backend = (Resolve-Path (Join-Path $PSScriptRoot '..\backend')).Path
$LogFile = Join-Path $Backend 'data\refresh.log'

# `python` on a fresh Windows is often the Microsoft Store stub; ask the real interpreter for its own path instead.
function Find-Python {
    if ($PythonPath) { return $PythonPath }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $exe = (& $py.Source -3 -c "import sys; print(sys.executable)" 2>$null)
        if ($exe) { return $exe.Trim() }
    }
    foreach ($c in (Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($c.Source -notlike '*\WindowsApps\*') { return $c.Source }
    }
    throw "No real Python found. Pass -PythonPath <full path to python.exe>"
}

function Show-Status {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Output "Task '$TaskName' is not installed."; return }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Output "Task:        $TaskName ($($task.State))"
    Write-Output "Last run:    $($info.LastRunTime)   result: $($info.LastTaskResult)  (0 = success)"
    Write-Output "Next run:    $($info.NextRunTime)"
    if (Test-Path $LogFile) {
        Write-Output "Log ($LogFile), last lines:"
        Get-Content $LogFile -Tail 6 | ForEach-Object { Write-Output "  $_" }
    } else {
        Write-Output "No log yet ($LogFile)."
    }
}

switch ($Action) {
    'install' {
        $python = Find-Python
        & $python -c "import nba_api, curl_cffi, fastapi" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "$python is missing packages; run: $python -m pip install -e `"$Backend[ingest]`"" }
        $pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
        if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to $python" }
        New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

        $act = New-ScheduledTaskAction -Execute $pythonw -Argument '-m nbadash.ingest refresh --log-file data\refresh.log' -WorkingDirectory $Backend
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Minutes) -RepetitionDuration (New-TimeSpan -Days 3650)
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger $trigger -Settings $settings -Force `
            -Description 'Refreshes the NBA dashboard database after games finish (nbadash.ingest refresh).' | Out-Null
        Write-Output "Installed '$TaskName': every $Minutes min, first run in about a minute."
        Show-Status
    }
    'uninstall' {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Output "Removed '$TaskName'."
        } else { Write-Output "Task '$TaskName' was not installed." }
    }
    'run' { Start-ScheduledTask -TaskName $TaskName; Write-Output "Started '$TaskName'." }
    'status' { Show-Status }
}
