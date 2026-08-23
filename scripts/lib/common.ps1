# Everreach local launcher  -  shared helpers.
#
# Dot-sourced by start-everreach.ps1, stop-everreach.ps1 and
# create-everreach-shortcuts.ps1. Nothing in here talks to Ollama,
# ComfyUI, the backend, or the frontend directly by name except in the
# small $Services table at the bottom, which the two orchestration
# scripts read to know where to look and what to launch.

$script:RepoRoot = Split-Path -Parent $PSScriptRoot | Split-Path -Parent
$script:RuntimeDir = Join-Path $RepoRoot ".runtime"
$script:LogDir = Join-Path $RuntimeDir "logs"
$script:StateFile = Join-Path $RuntimeDir "state.json"

function Initialize-RuntimeDirs {
    if (-not (Test-Path $script:RuntimeDir)) { New-Item -ItemType Directory -Path $script:RuntimeDir -Force | Out-Null }
    if (-not (Test-Path $script:LogDir)) { New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null }
}

# State file shape: { "<service>": { Pid, StartTime (round-trip "o"
# string), CommandMatch, StartedByLauncher } , ... }. Read as a plain
# hashtable so callers can index/assign with $state["ollama"] freely.
function Read-LauncherState {
    if (-not (Test-Path $script:StateFile)) { return @{} }
    try {
        $raw = Get-Content -Raw -Path $script:StateFile -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Warning "Runtime state file was unreadable/corrupt; starting from a clean state. ($script:StateFile)"
        return @{}
    }
    $state = @{}
    if ($null -eq $raw) { return $state }
    foreach ($prop in $raw.PSObject.Properties) {
        $entry = $prop.Value
        $state[$prop.Name] = @{
            Pid               = $entry.Pid
            StartTime         = $entry.StartTime
            CommandMatch      = $entry.CommandMatch
            StartedByLauncher = [bool]$entry.StartedByLauncher
        }
    }
    return $state
}

function Write-LauncherState {
    param([hashtable]$State)
    Initialize-RuntimeDirs
    ($State | ConvertTo-Json -Depth 5) | Set-Content -Path $script:StateFile -Encoding utf8
}

function Test-PortOpen {
    param([string]$ComputerName = "127.0.0.1", [int]$Port, [int]$TimeoutMs = 500)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($ComputerName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs)
        if ($ok -and $client.Connected) { return $true }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

# Returns "READY" (our own health endpoint answered 2xx), "OCCUPIED"
# (something answered HTTP on that port, but not what we expect  -  a
# port conflict, never blindly overwritten) or "DOWN" (nothing there).
function Test-ServiceState {
    param([string]$HealthUrl, [int]$Port, [int]$TimeoutSec = 3)
    try {
        Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop | Out-Null
        return "READY"
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { return "OCCUPIED" }
        if (Test-PortOpen -Port $Port) { return "OCCUPIED" }
        return "DOWN"
    } catch {
        if (Test-PortOpen -Port $Port) { return "OCCUPIED" }
        return "DOWN"
    }
}

function Wait-ForServiceReady {
    param([string]$HealthUrl, [int]$Port, [int]$MaxWaitSec, [int]$PollIntervalSec = 2)
    $deadline = (Get-Date).AddSeconds($MaxWaitSec)
    while ((Get-Date) -lt $deadline) {
        $state = Test-ServiceState -HealthUrl $HealthUrl -Port $Port
        if ($state -eq "READY") { return "READY" }
        if ($state -eq "OCCUPIED") { return "OCCUPIED" }
        Start-Sleep -Seconds $PollIntervalSec
    }
    return "TIMEOUT"
}

# A stored PID is only trusted if the process still exists AND its
# StartTime matches exactly AND its command line still looks like the
# thing we started  -  three independent checks so PID reuse by an
# unrelated process can never be mistaken for our own child.
function Test-OwnedProcessValid {
    param([hashtable]$Entry)
    if (-not $Entry -or -not $Entry.Pid) { return $false }
    $proc = Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    try {
        $actualStart = $proc.StartTime.ToString("o")
    } catch {
        return $false
    }
    if ($actualStart -ne $Entry.StartTime) { return $false }
    if ($Entry.CommandMatch) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$($Entry.Pid)" -ErrorAction SilentlyContinue
        if (-not $cim -or -not $cim.CommandLine -or ($cim.CommandLine -notlike "*$($Entry.CommandMatch)*")) { return $false }
    }
    return $true
}

function New-TrackedProcess {
    param(
        [string]$Exe,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$LogName
    )
    Initialize-RuntimeDirs
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outLog = Join-Path $script:LogDir "$LogName`_$timestamp.out.log"
    $errLog = Join-Path $script:LogDir "$LogName`_$timestamp.err.log"

    $proc = Start-Process -FilePath $Exe -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru

    return @{
        Process = $proc
        OutLog  = $outLog
        ErrLog  = $errLog
    }
}

# Graceful-then-forceful stop. Windows gives console processes with no
# window no real graceful-shutdown signal from plain PowerShell, so
# "graceful" here means: ask once, give it a few seconds, then -Force.
function Stop-OwnedProcess {
    param([int]$ProcessId, [int]$GraceSeconds = 5)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $true }
    try { Stop-Process -Id $ProcessId -ErrorAction Stop } catch { }
    $deadline = (Get-Date).AddSeconds($GraceSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 300
    }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc) {
        try { Stop-Process -Id $ProcessId -Force -ErrorAction Stop } catch { }
        Start-Sleep -Milliseconds 300
    }
    return -not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

# The one place that knows where everything lives. Paths outside the
# repo (Ollama's install, ComfyUI's E:\RPG layout) are read here, never
# guessed at the call site.
function Get-EverreachServiceDefinitions {
    $backendDir = Join-Path $script:RepoRoot "backend"
    $frontendDir = Join-Path $script:RepoRoot "frontend"
    $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    $viteJs = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
    $backendPython = Join-Path $backendDir ".venv\Scripts\python.exe"

    return @{
        ollama = @{
            Label        = "Ollama"
            HealthUrl    = "http://127.0.0.1:11434/api/version"
            Port         = 11434
            Required     = $false
            Exe          = $ollamaExe
            ArgumentList = @("serve")
            WorkingDir   = Split-Path $ollamaExe
            CommandMatch = "ollama.exe"
            LogName      = "ollama"
            MaxWaitSec   = 30
        }
        comfyui = @{
            Label        = "ComfyUI"
            HealthUrl    = "http://127.0.0.1:8188/system_stats"
            Port         = 8188
            Required     = $false
            Exe          = "E:\RPG\ComfyUI\.venv\Scripts\python.exe"
            ArgumentList = @(
                "E:\RPG\ComfyUI\main.py",
                "--base-directory", "E:\RPG\ComfyData",
                "--database-url", "sqlite:///E:/RPG/ComfyData/user/comfyui.db",
                "--listen", "127.0.0.1",
                "--port", "8188"
            )
            WorkingDir   = "E:\RPG"
            CommandMatch = "ComfyUI\main.py"
            LogName      = "comfyui"
            MaxWaitSec   = 90
        }
        backend = @{
            Label        = "Backend"
            HealthUrl    = "http://127.0.0.1:8000/api/health"
            Port         = 8000
            Required     = $true
            Exe          = $backendPython
            ArgumentList = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
            WorkingDir   = $backendDir
            CommandMatch = "uvicorn"
            LogName      = "backend"
            MaxWaitSec   = 30
        }
        frontend = @{
            Label        = "Frontend"
            HealthUrl    = "http://127.0.0.1:5173/"
            Port         = 5173
            Required     = $true
            Exe          = (Get-Command node -ErrorAction SilentlyContinue).Source
            ArgumentList = @($viteJs, "--host", "127.0.0.1", "--port", "5173")
            WorkingDir   = $frontendDir
            CommandMatch = "vite\bin\vite.js"
            LogName      = "frontend"
            MaxWaitSec   = 30
        }
    }
}

$script:GameUrl = "http://127.0.0.1:5173/"
