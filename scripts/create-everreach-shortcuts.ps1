<#
.SYNOPSIS
    Creates "Everreach" and "Stop Everreach" shortcuts on the current
    user's Desktop, pointing at start-everreach.ps1 / stop-everreach.ps1.

.DESCRIPTION
    Run this once. The shortcuts invoke powershell.exe with a per-process
    -ExecutionPolicy Bypass (the machine/user execution policy is never
    changed) and an explicitly quoted, absolute path, so they work
    correctly even if the repository path contains spaces.

    frontend/public/images/icon.png is the source app image. Windows
    shortcut icons require an .ico file (a raw .png is not accepted by
    IShellLink.IconLocation), so a single 256x256 .ico is generated on
    demand into .runtime/icon.ico  -  a derived, gitignored build
    artifact, not a new repository asset.
#>

. "$PSScriptRoot\lib\common.ps1"

function Convert-PngToIco {
    param([string]$PngPath, [string]$IcoPath, [int]$Size = 256)
    Add-Type -AssemblyName System.Drawing

    $src = [System.Drawing.Image]::FromFile($PngPath)
    $square = New-Object System.Drawing.Bitmap $Size, $Size
    $g = [System.Drawing.Graphics]::FromImage($square)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.DrawImage($src, 0, 0, $Size, $Size)
    $g.Dispose()
    $src.Dispose()

    $pngStream = New-Object System.IO.MemoryStream
    $square.Save($pngStream, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngBytes = $pngStream.ToArray()
    $square.Dispose()
    $pngStream.Dispose()

    # Minimal single-image ICO container (PNG-compressed frame, fully
    # supported by Windows Explorer/shell links since Vista): ICONDIR
    # (6 bytes) + one ICONDIRENTRY (16 bytes) + the raw PNG bytes.
    $fs = [System.IO.File]::Open($IcoPath, [System.IO.FileMode]::Create)
    $bw = New-Object System.IO.BinaryWriter($fs)
    try {
        $bw.Write([UInt16]0)      # reserved
        $bw.Write([UInt16]1)      # type: icon
        $bw.Write([UInt16]1)      # image count
        $bw.Write([byte]0)        # width (0 = 256)
        $bw.Write([byte]0)        # height (0 = 256)
        $bw.Write([byte]0)        # color count
        $bw.Write([byte]0)        # reserved
        $bw.Write([UInt16]1)      # color planes
        $bw.Write([UInt16]32)     # bits per pixel
        $bw.Write([UInt32]$pngBytes.Length)
        $bw.Write([UInt32]22)     # offset: 6 (ICONDIR) + 16 (ICONDIRENTRY)
        $bw.Write($pngBytes)
    } finally {
        $bw.Flush()
        $bw.Close()
        $fs.Close()
    }
}

$iconPng = Join-Path $script:RepoRoot "frontend\public\images\icon.png"
$iconIco = Join-Path $script:RuntimeDir "icon.ico"
$iconLocation = $null

if (Test-Path $iconPng) {
    Initialize-RuntimeDirs
    $needsRegen = (-not (Test-Path $iconIco)) -or ((Get-Item $iconPng).LastWriteTime -gt (Get-Item $iconIco).LastWriteTime)
    if ($needsRegen) {
        try {
            Convert-PngToIco -PngPath $iconPng -IcoPath $iconIco
            Write-Host "Generated shortcut icon at $iconIco" -ForegroundColor DarkGray
        } catch {
            Write-Warning "Could not convert $iconPng to an .ico ($($_.Exception.Message))  -  shortcuts will use the default icon."
        }
    }
    if (Test-Path $iconIco) { $iconLocation = "$iconIco,0" }
} else {
    Write-Host "No icon found at $iconPng  -  shortcuts will use the default icon." -ForegroundColor DarkGray
}

$powershellExe = Join-Path $PSHOME "powershell.exe"
$startScript = Join-Path $script:RepoRoot "scripts\start-everreach.ps1"
$stopScript = Join-Path $script:RepoRoot "scripts\stop-everreach.ps1"
$desktop = [Environment]::GetFolderPath("Desktop")
$wsh = New-Object -ComObject WScript.Shell

$everreachLnk = $wsh.CreateShortcut((Join-Path $desktop "Everreach.lnk"))
$everreachLnk.TargetPath = $powershellExe
$everreachLnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$startScript`""
$everreachLnk.WorkingDirectory = $script:RepoRoot
$everreachLnk.Description = "Start the local Everreach stack and open the game"
if ($iconLocation) { $everreachLnk.IconLocation = $iconLocation }
$everreachLnk.Save()
Write-Host "Created shortcut: $($everreachLnk.FullName)" -ForegroundColor Green

$stopLnk = $wsh.CreateShortcut((Join-Path $desktop "Stop Everreach.lnk"))
$stopLnk.TargetPath = $powershellExe
$stopLnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$stopScript`""
$stopLnk.WorkingDirectory = $script:RepoRoot
$stopLnk.Description = "Stop the local Everreach services this launcher started"
if ($iconLocation) { $stopLnk.IconLocation = $iconLocation }
$stopLnk.Save()
Write-Host "Created shortcut: $($stopLnk.FullName)" -ForegroundColor Green

Write-Host ""
Write-Host "Double-click 'Everreach' on the Desktop to start playing." -ForegroundColor Cyan
