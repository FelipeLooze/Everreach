<#
.SYNOPSIS
    Stops only the Everreach services that start-everreach.ps1 actually
    launched itself. Anything that was already running before the
    launcher touched it (a pre-existing Ollama/ComfyUI, most commonly)
    is left running.

.DESCRIPTION
    Every stop candidate is re-validated against .runtime/state.json
    immediately before being touched: the stored PID must still exist
    AND its process StartTime must still match exactly AND its command
    line must still look like the thing we started. A stale entry (the
    process already exited, or its PID was reused by something else) is
    reported and dropped from the state file, never killed.
#>

. "$PSScriptRoot\lib\common.ps1"

Write-Host ""
Write-Host "Everreach Launcher  -  Stop" -ForegroundColor Cyan
Write-Host ""

$services = Get-EverreachServiceDefinitions
$state = Read-LauncherState

if ($state.Count -eq 0) {
    Write-Host "Nothing tracked in .runtime\state.json  -  nothing to stop." -ForegroundColor DarkGray
    exit 0
}

# Stop game-facing services first, then the shared AI services  -  the
# reverse of startup order.
foreach ($key in @("frontend", "backend", "comfyui", "ollama")) {
    $svc = $services[$key]
    $entry = $state[$key]

    if (-not $entry) {
        Write-Host "$($svc.Label.PadRight(12)) not tracked as launcher-owned  -  left as-is." -ForegroundColor DarkGray
        continue
    }

    if (-not $entry.StartedByLauncher) {
        Write-Host "$($svc.Label.PadRight(12)) was not started by the launcher  -  left running." -ForegroundColor DarkGray
        $state.Remove($key)
        continue
    }

    if (-not (Test-OwnedProcessValid -Entry $entry)) {
        Write-Host "$($svc.Label.PadRight(12)) stored PID $($entry.Pid) no longer matches (already exited, or reused)  -  skipping, not killed." -ForegroundColor Yellow
        $state.Remove($key)
        continue
    }

    $stopped = Stop-OwnedProcess -ProcessId $entry.Pid
    if ($stopped) {
        Write-Host "$($svc.Label.PadRight(12)) stopped (pid $($entry.Pid))." -ForegroundColor Green
    } else {
        Write-Host "$($svc.Label.PadRight(12)) could not be stopped (pid $($entry.Pid) still present)  -  check it manually." -ForegroundColor Red
    }
    $state.Remove($key)
}

Write-LauncherState -State $state
Write-Host ""
