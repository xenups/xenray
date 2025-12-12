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

# Wait for main process to exit (max 30 seconds)
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

Write-Host "XenRay Updater: Extracting update..."

try {
    # Extract ZIP to app directory
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
    [System.Windows.Forms.MessageBox]::Show("Update failed: $_", "XenRay Update Error")
}

# Clean up this script
Start-Sleep -Seconds 2
Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
