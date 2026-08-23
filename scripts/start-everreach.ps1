<#
.SYNOPSIS
    Starts the local Everreach stack (Ollama, ComfyUI, backend, frontend)
    and opens the game in the default browser.

.DESCRIPTION
    Idempotent: a service already answering its own health check is left
    alone. Only services this run actually launches are recorded in
    .runtime/state.json, so a later stop-everreach.ps1 never touches a
    process it didn't start (including one started by an earlier run of
    this same script  -  ownership survives across runs, see
    Test-OwnedProcessValid in lib/common.ps1).

    Backend and frontend are required: the browser only opens once both
    are ready. Ollama and ComfyUI are optional local AI services  -  a
    failure to start either is reported clearly but never blocks the
    game from opening (ComfyUI failure != gameplay failure; Ollama
    failure just means mechanical/fallback narration, per the app's own
    existing behavior).

.PARAMETER NoBrowser
    Start the stack but do not open a browser tab. Useful for
    development when you only want the servers running.
#>
param(
    [switch]$NoBrowser
)

. "$PSScriptRoot\lib\common.ps1"

Write-Host ""
Write-Host "Everreach Launcher" -ForegroundColor Cyan
Write-Host ""

$services = Get-EverreachServiceDefinitions
$state = Read-LauncherState
$results = [ordered]@{}

foreach ($key in @("ollama", "comfyui", "backend", "frontend")) {
    $svc = $services[$key]
    $currentState = Test-ServiceState -HealthUrl $svc.HealthUrl -Port $svc.Port

    if ($currentState -eq "READY") {
        # Already up. Only keep claiming ownership if a PREVIOUS run of
        # this launcher owns the exact process still answering here  - 
        # never claim a service we didn't verifiably start ourselves.
        $existing = $state[$key]
        if ($existing -and $existing.StartedByLauncher -and (Test-OwnedProcessValid -Entry $existing)) {
            $state[$key] = $existing
            $results[$key] = "READY (already running, launcher-owned)"
        } else {
            $state.Remove($key)
            $results[$key] = "READY (already running)"
        }
        continue
    }

    if ($currentState -eq "OCCUPIED") {
        $state.Remove($key)
        $results[$key] = "PORT $($svc.Port) OCCUPIED BY UNKNOWN/UNEXPECTED SERVICE"
        continue
    }

    # DOWN  -  start it, unless the executable itself can't be found.
    if (-not $svc.Exe -or -not (Test-Path $svc.Exe)) {
        $state.Remove($key)
        $results[$key] = "NOT FOUND (expected at: $($svc.Exe))"
        continue
    }

    Write-Host "Starting $($svc.Label)..." -ForegroundColor DarkGray
    $tracked = New-TrackedProcess -Exe $svc.Exe -ArgumentList $svc.ArgumentList -WorkingDirectory $svc.WorkingDir -LogName $svc.LogName
    $waitResult = Wait-ForServiceReady -HealthUrl $svc.HealthUrl -Port $svc.Port -MaxWaitSec $svc.MaxWaitSec

    if ($waitResult -eq "READY") {
        $state[$key] = @{
            Pid               = $tracked.Process.Id
            StartTime         = $tracked.Process.StartTime.ToString("o")
            CommandMatch      = $svc.CommandMatch
            StartedByLauncher = $true
        }
        $results[$key] = "READY (started, pid $($tracked.Process.Id))"
    } elseif ($waitResult -eq "OCCUPIED") {
        $state.Remove($key)
        $results[$key] = "PORT $($svc.Port) OCCUPIED BY UNKNOWN/UNEXPECTED SERVICE"
    } else {
        $state.Remove($key)
        $results[$key] = "FAILED TO START (see logs: $($tracked.OutLog) / $($tracked.ErrLog))"
    }
}

Write-LauncherState -State $state

Write-Host ""
foreach ($key in @("ollama", "comfyui", "backend", "frontend")) {
    $svc = $services[$key]
    $label = $svc.Label.PadRight(12)
    $status = $results[$key]
    $color = if ($status -like "READY*") { "Green" } elseif ($svc.Required) { "Red" } else { "Yellow" }
    Write-Host "$label $status" -ForegroundColor $color
}
Write-Host ""

$backendReady = $results["backend"] -like "READY*"
$frontendReady = $results["frontend"] -like "READY*"

if (-not $backendReady -or -not $frontendReady) {
    Write-Host "Backend and/or frontend are not ready  -  not opening the browser." -ForegroundColor Red
    Write-Host "Check the logs under .runtime\logs for details." -ForegroundColor Red
    exit 1
}

if ($results["comfyui"] -notlike "READY*") {
    Write-Host "Note: ComfyUI is unavailable  -  visual generation will be unavailable, gameplay is unaffected." -ForegroundColor Yellow
}
if ($results["ollama"] -notlike "READY*") {
    Write-Host "Note: Ollama is unavailable  -  narration will fall back to mechanical/introductory text (narrator_unavailable)." -ForegroundColor Yellow
}

if (-not $NoBrowser) {
    Write-Host "Opening Everreach..." -ForegroundColor Cyan
    Start-Process $script:GameUrl
} else {
    Write-Host "Services are ready ($script:GameUrl)  -  -NoBrowser was passed, not opening a browser tab." -ForegroundColor Cyan
}
