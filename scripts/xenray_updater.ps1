# XenRay Auto-Updater Script
# This script updates XenRay and restarts it
# Usage: xenray_updater.ps1 <ProcessID> <ZipPath> <AppDir> <ExePath>

param(
    [Parameter(Mandatory=$true)]
    [int]$ProcessID,

    [Parameter(Mandatory=$true)]
    [string]$ZipPath,

    [Parameter(Mandatory=$true)]
    [string]$AppDir,

    [Parameter(Mandatory=$true)]
    [string]$ExePath
)

$ErrorActionPreference = "Stop"

Write-Host "XenRay Updater: Waiting for main process to exit..."

# Wait for main process to exit (max 30 seconds), then force-kill if it lingers
# so the packed EXE is released before we try to overwrite it.
$timeout = 30
$elapsed = 0
while ($elapsed -lt $timeout) {
    $process = Get-Process -Id $ProcessID -ErrorAction SilentlyContinue
    if (-not $process) {
        break
    }
    Start-Sleep -Seconds 1
    $elapsed++
}

# If the app is still alive after the grace period, forcibly terminate it.
$stillRunning = Get-Process -Id $ProcessID -ErrorAction SilentlyContinue
if ($stillRunning) {
    Write-Host "XenRay Updater: Main process still running; terminating it to release file locks."
    Stop-Process -Id $ProcessID -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Pre-flight: if the target EXE still exists, clear its read-only flag so the
# overwrite below cannot fail on a locked/readonly packed binary.
if (Test-Path -LiteralPath $ExePath) {
    Remove-Item -LiteralPath $ExePath -Force -ErrorAction SilentlyContinue
}
# Also remove the previous .old backup so a stale one can't block the rename.
$old = "$ExePath.old"
if (Test-Path -LiteralPath $old) {
    Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
}

Write-Host "XenRay Updater: Extracting update..."

try {
    # Extract the new zip over the app directory (does NOT remove unrelated files).
    Expand-Archive -Path $ZipPath -DestinationPath $AppDir -Force

    Write-Host "XenRay Updater: Update extracted successfully"

    # Clean up ZIP file
    Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue

    # Restart application
    Write-Host "XenRay Updater: Restarting application..."
    Start-Process -FilePath $ExePath

    Write-Host "XenRay Updater: Update complete!"

} catch {
    Write-Host "XenRay Updater: Error - $_"
    try {
        [System.Windows.Forms.MessageBox]::Show("Update failed: $_", "XenRay Update Error")
    } catch {
        Write-Host "XenRay Updater: Could not show error dialog."
    }
}

# Clean up this script
Start-Sleep -Seconds 2
Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
