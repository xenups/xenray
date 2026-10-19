"""App Update Service.

This service handles checking for and installing application updates from GitHub releases.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests
from loguru import logger

from src.core.constants import APP_VERSION, GITHUB_REPO, UPDATE_DOWNLOAD_TIMEOUT, UPDATE_MIN_FILE_SIZE
from src.utils.platform_utils import PlatformUtils

# API URL constructed from configurable repo
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

_EMBEDDED_UPDATER_SCRIPT = r"""# XenRay Auto-Updater Script
# This script updates XenRay and restarts it
# Usage: xenray_updater.ps1 -ProcessID <int> -ZipPath <string> -AppDir <string> -ExePath <string>

param(
    [Parameter(Mandatory=$false)]
    [int]$ProcessID = 0,

    [Parameter(Mandatory=$true)]
    [string]$ZipPath,

    [Parameter(Mandatory=$true)]
    [string]$AppDir,

    [Parameter(Mandatory=$true)]
    [string]$ExePath,

    [Parameter(Mandatory=$false)]
    [switch]$SuppressDialog = $false
)

$ErrorActionPreference = "Continue"

# Setup persistent logging in TEMP
$logPath = Join-Path ([System.IO.Path]::GetTempPath()) "xenray_updater.log"
function Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line
    try {
        Add-Content -Path $logPath -Value $line -ErrorAction SilentlyContinue
    } catch {}
}

Log "=== XenRay Auto-Updater Started ==="
Log "ProcessID: $ProcessID"
Log "ZipPath: $ZipPath"
Log "AppDir: $AppDir"
Log "ExePath: $ExePath"

# Ensure Windows Forms is available for alerts if needed
try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
} catch {}

# Helper: Fail-closed process termination scoped strictly to TargetAppDir
function Stop-XenrayProcessesInsideAppDir {
    param(
        [Parameter(Mandatory=$true)]
        [string]$TargetAppDir,

        [Parameter(Mandatory=$false)]
        [int]$CallerProcessID = 0
    )

    try {
        $normAppDir = [System.IO.Path]::GetFullPath($TargetAppDir)
    } catch {
        Log "WARNING: Could not normalize TargetAppDir '$TargetAppDir': $_. Preserving all processes."
        return
    }

    if (-not $normAppDir.EndsWith([System.IO.Path]::DirectorySeparatorChar.ToString())) {
        $normAppDir += [System.IO.Path]::DirectorySeparatorChar
    }

    $candidateProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
    $targetNames = @("XenRay", "xray", "sing-box", "xray-parser", "udpgw-server")
    foreach ($name in $targetNames) {
        $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($p in $procs) {
                if (-not ($candidateProcesses | Where-Object { $_.Id -eq $p.Id })) {
                    $candidateProcesses.Add($p)
                }
            }
        }
    }

    if ($CallerProcessID -gt 0) {
        $caller = Get-Process -Id $CallerProcessID -ErrorAction SilentlyContinue
        if ($caller -and -not ($candidateProcesses | Where-Object { $_.Id -eq $caller.Id })) {
            $candidateProcesses.Add($caller)
        }
    }

    foreach ($p in $candidateProcesses) {
        $pName = $p.ProcessName
        $procId = $p.Id
        $pPath = $null
        try {
            if ($p.MainModule -and $p.MainModule.FileName) {
                $pPath = $p.MainModule.FileName
            } elseif ($p.Path) {
                $pPath = $p.Path
            }
        } catch {
            $pPath = $null
        }

        if (-not $pPath) {
            Log "WARNING: Inaccessible or missing executable path for process $pName (PID: $procId). Preserving process."
            continue
        }

        $normPPath = $null
        try {
            $normPPath = [System.IO.Path]::GetFullPath($pPath)
        } catch {
            Log "WARNING: Could not normalize path '$pPath' for PID $procId. Preserving process."
            continue
        }

        if ($normPPath.StartsWith($normAppDir, [System.StringComparison]::OrdinalIgnoreCase)) {
            Log "Terminating process inside AppDir: $pName (PID: $procId, Path: $normPPath)"
            $p | Stop-Process -Force -ErrorAction SilentlyContinue
        } else {
            Log "Preserving process $pName (PID: $procId) located outside AppDir: $normPPath"
        }
    }
}

# Helper: Pure decision logic for XenRay TUN route eligibility
function Test-IsXenrayTunRouteEligible {
    param(
        [string]$DestinationPrefix,
        [string]$NextHop,
        [string]$InterfaceAlias,
        [string]$InterfaceDescription
    )

    # 1. Must be a default route
    if ($DestinationPrefix -ne "0.0.0.0/0" -and $DestinationPrefix -ne "0.0.0.0") {
        return $false
    }

    # 2. Must target a XenRay TUN gateway IP
    $isTunGateway = ($NextHop -in @("10.0.0.2", "10.0.0.1", "0.0.0.0"))
    if (-not $isTunGateway) {
        return $false
    }

    # 3. Guard against missing or inaccessible adapter identity
    if ([string]::IsNullOrWhiteSpace($InterfaceAlias) -and [string]::IsNullOrWhiteSpace($InterfaceDescription)) {
        return $false
    }

    $alias = if ($InterfaceAlias) { $InterfaceAlias.Trim() } else { "" }
    $desc = if ($InterfaceDescription) { $InterfaceDescription.Trim() } else { "" }

    # 4. Conflicting third-party or physical indicators must be preserved
    $conflictingPatterns = @("openvpn", "wireguard", "tailscale", "zerotier", "nordlynx", "hyper-v", "vethernet", "virtualbox", "vmware", "intel", "realtek", "broadcom", "qualcomm")
    foreach ($pat in $conflictingPatterns) {
        if ($alias -match "(?i)$pat" -or $desc -match "(?i)$pat") {
            return $false
        }
    }

    # 5. Positive unambiguous identification of XenRay TUN adapter
    $isExplicitTunAlias = ($alias -in @("SINGTUN", "xenray-tun"))
    $isExplicitTunDesc = ($desc -match "(?i)^sing-tun" -or $desc -match "(?i)sing-tun Tunnel" -or $desc -match "(?i)^wintun")
    $isTunAdapter = ($isExplicitTunAlias -or $isExplicitTunDesc)

    return [bool]$isTunAdapter
}

# Helper: Create pre-update backup and record pre-existing files manifest
function New-XenrayBackupManifest {
    param(
        [Parameter(Mandatory=$true)]
        [string]$AppDir,

        [Parameter(Mandatory=$true)]
        [string]$BackupDir,

        [Parameter(Mandatory=$true)]
        [string]$ContentRoot
    )

    $manifest = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

    if (Test-Path -LiteralPath $AppDir) {
        $normAppDirPrefix = [System.IO.Path]::GetFullPath($AppDir)
        if (-not $normAppDirPrefix.EndsWith([System.IO.Path]::DirectorySeparatorChar.ToString())) {
            $normAppDirPrefix += [System.IO.Path]::DirectorySeparatorChar
        }

        Get-ChildItem -LiteralPath $ContentRoot | ForEach-Object {
            $destPath = Join-Path $AppDir $_.Name
            if (Test-Path -LiteralPath $destPath) {
                Copy-Item -LiteralPath $destPath -Destination $BackupDir -Recurse -Force
                if (Test-Path -LiteralPath $destPath -PathType Container) {
                    Get-ChildItem -LiteralPath $destPath -Recurse -File | ForEach-Object {
                        $normFull = [System.IO.Path]::GetFullPath($_.FullName)
                        if ($normFull.StartsWith($normAppDirPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                            $rel = $normFull.Substring($normAppDirPrefix.Length)
                            [void]$manifest.Add($rel)
                        }
                    }
                } else {
                    [void]$manifest.Add($_.Name)
                }
            }
        }
    }
    return $manifest
}

# Helper: Rollback implementation restoring backed up files and pruning newly introduced files
function Invoke-XenrayRollback {
    param(
        [Parameter(Mandatory=$true)]
        [string]$AppDir,

        [Parameter(Mandatory=$true)]
        [string]$BackupDir,

        [Parameter(Mandatory=$true)]
        [string]$ContentRoot,

        [Parameter(Mandatory=$false)]
        [System.Collections.Generic.HashSet[string]]$PreExistingFiles = $null
    )

    if (-not (Test-Path -LiteralPath $BackupDir)) {
        Log "ERROR: Backup directory not found for rollback: $BackupDir"
        return $false
    }

    if (-not $PreExistingFiles) {
        $PreExistingFiles = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    }

    try {
        # 1. Restore backed-up pre-existing files
        Get-ChildItem -LiteralPath $BackupDir | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $AppDir -Recurse -Force -ErrorAction Stop
        }
        Log "Restored backed-up files from backup directory."

        # 2. Remove files introduced by this failed update that did not exist before
        $normAppDirPrefix = [System.IO.Path]::GetFullPath($AppDir)
        if (-not $normAppDirPrefix.EndsWith([System.IO.Path]::DirectorySeparatorChar.ToString())) {
            $normAppDirPrefix += [System.IO.Path]::DirectorySeparatorChar
        }

        Get-ChildItem -LiteralPath $ContentRoot | ForEach-Object {
            $destPath = Join-Path $AppDir $_.Name
            if (Test-Path -LiteralPath $destPath) {
                if (Test-Path -LiteralPath $destPath -PathType Container) {
                    Get-ChildItem -LiteralPath $destPath -Recurse -File | ForEach-Object {
                        $normFull = [System.IO.Path]::GetFullPath($_.FullName)
                        if ($normFull.StartsWith($normAppDirPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                            $rel = $normFull.Substring($normAppDirPrefix.Length)
                            if (-not $PreExistingFiles.Contains($rel)) {
                                Log "Rollback: Removing newly introduced file: $rel"
                                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
                            }
                        }
                    }
                    # Prune newly introduced empty directories
                    Get-ChildItem -LiteralPath $destPath -Recurse -Directory | Sort-Object -Property FullName -Descending | ForEach-Object {
                        if ((Get-ChildItem -LiteralPath $_.FullName -Force).Count -eq 0) {
                            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
                        }
                    }
                    if ((Get-ChildItem -LiteralPath $destPath -Force).Count -eq 0) {
                        Remove-Item -LiteralPath $destPath -Force -Recurse -ErrorAction SilentlyContinue
                    }
                } else {
                    if (-not $PreExistingFiles.Contains($_.Name)) {
                        Log "Rollback: Removing newly introduced file: $($_.Name)"
                        Remove-Item -LiteralPath $destPath -Force -ErrorAction Stop
                    }
                }
            }
        }
        return $true
    } catch {
        Log "CRITICAL: Rollback failed: $_"
        return $false
    }
}

# Helper: Handle deployment failure by executing rollback, logging status, and ensuring backup retention
function Invoke-XenrayDeploymentFailure {
    param(
        [Parameter(Mandatory=$true)]
        [string]$AppDir,

        [Parameter(Mandatory=$true)]
        [string]$BackupDir,

        [Parameter(Mandatory=$true)]
        [string]$ContentRoot,

        [Parameter(Mandatory=$false)]
        [System.Collections.Generic.HashSet[string]]$PreExistingFiles = $null,

        [Parameter(Mandatory=$false)]
        [switch]$SuppressDialog = $false
    )

    Log "CRITICAL: Could not copy all updated files to $AppDir after retry attempts."
    Log "Initiating rollback to previous installation from: $BackupDir..."
    $rollbackSuccess = Invoke-XenrayRollback -AppDir $AppDir -BackupDir $BackupDir -ContentRoot $ContentRoot -PreExistingFiles $PreExistingFiles
    if ($rollbackSuccess) {
        Log "Rollback completed: Previous installation restored and newly introduced files pruned."
        if (-not $SuppressDialog) {
            try {
                [System.Windows.Forms.MessageBox]::Show(
                    "The update could not be completed and has been rolled back to your previous version. Please close any background processes and try again.",
                    "XenRay Update Rollback",
                    0, 48
                )
            } catch {}
        }
    } else {
        Log "CRITICAL: Rollback failed. Preserving backup directory at: $BackupDir"
        if (-not $SuppressDialog) {
            try {
                [System.Windows.Forms.MessageBox]::Show(
                    "The update failed and rollback could not fully restore your files. A backup is preserved at:`n$BackupDir`nPlease restore manually or reinstall.",
                    "XenRay Update Error",
                    0, 16
                )
            } catch {}
        }
    }
    return $rollbackSuccess
}

# 1. Wait for main process to exit (graceful wait up to 6 seconds)
if ($ProcessID -gt 0) {
    Log "Waiting for main process ($ProcessID) to terminate..."
    $elapsed = 0
    while ($elapsed -lt 6) {
        $p = Get-Process -Id $ProcessID -ErrorAction SilentlyContinue
        if (-not $p) { break }
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
    }
}

# 2. Terminate any lingering XenRay and Core processes strictly inside AppDir
Log "Ensuring lingering processes inside AppDir are terminated..."
Stop-XenrayProcessesInsideAppDir -TargetAppDir $AppDir -CallerProcessID $ProcessID
Start-Sleep -Seconds 1

# 3. Clean up any broken XenRay TUN routes if present (with strict ownership check)
Log "Checking for orphaned XenRay TUN default routes..."
try {
    $defaultRoutes = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
    if ($defaultRoutes) {
        $tunCleaned = 0
        foreach ($r in $defaultRoutes) {
            $adapter = Get-NetAdapter -InterfaceIndex $r.InterfaceIndex -ErrorAction SilentlyContinue
            $alias = if ($adapter) { $adapter.Name } else { $r.InterfaceAlias }
            $desc = if ($adapter) { $adapter.InterfaceDescription } else { "" }

            if (Test-IsXenrayTunRouteEligible -DestinationPrefix $r.DestinationPrefix -NextHop $r.NextHop -InterfaceAlias $alias -InterfaceDescription $desc) {
                Log "Found orphan XenRay TUN default route: Interface='$alias' ($desc), Index=$($r.InterfaceIndex), NextHop='$($r.NextHop)'. Removing..."
                try {
                    Remove-NetRoute -DestinationPrefix "0.0.0.0/0" -InterfaceIndex $r.InterfaceIndex -NextHop $r.NextHop -Confirm:$false -ErrorAction Stop
                    Log "SUCCESS: Removed orphan XenRay TUN default route on interface '$alias'."
                    $tunCleaned++
                } catch {
                    Log "WARNING: Remove-NetRoute failed ($($_.Exception.Message)), attempting scoped route delete..."
                    route delete 0.0.0.0 mask 0.0.0.0 $($r.NextHop) if $($r.InterfaceIndex) 2>&1 | Out-String | ForEach-Object { if ($_.Trim()) { Log "route delete: $_" } }
                }
            } elseif ($r.NextHop -in @("10.0.0.2", "10.0.0.1")) {
                Log "WARNING: Default route with NextHop $($r.NextHop) found on interface '$alias' ($desc), but interface is NOT unambiguously a XenRay TUN adapter. Leaving route untouched."
            }
        }
        if ($tunCleaned -eq 0) {
            Log "No orphan XenRay TUN default routes required removal."
        }
    } else {
        Log "No default routes detected by Get-NetRoute."
    }
} catch {
    Log "WARNING: Route check encountered an error: $_"
}

# 4. Verify ZIP archive exists
if (-not (Test-Path -LiteralPath $ZipPath)) {
    Log "ERROR: ZIP archive not found at $ZipPath"
    [System.Windows.Forms.MessageBox]::Show("Update archive was not found. Please try updating again.", "XenRay Update Error", 0, 16)
    exit 1
}

# 5. Extract to temporary staging folder first (atomic & safe)
$stagingDir = Join-Path ([System.IO.Path]::GetTempPath()) ("xenray_staging_" + [System.Guid]::NewGuid().ToString("N"))
Log "Extracting ZIP to staging directory: $stagingDir"

try {
    if (Test-Path -LiteralPath $stagingDir) {
        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $stagingDir -Force
    Log "Extraction to staging succeeded."
} catch {
    Log "ERROR extracting ZIP to staging: $_"
    [System.Windows.Forms.MessageBox]::Show("Failed to extract update package: $_", "XenRay Update Error", 0, 16)
    exit 1
}

# 6. Locate source directory inside staging
$contentRoot = $stagingDir
if (Test-Path (Join-Path $stagingDir "package")) {
    $contentRoot = Join-Path $stagingDir "package"
} elseif (Test-Path (Join-Path $stagingDir "XenRay")) {
    $contentRoot = Join-Path $stagingDir "XenRay"
}
Log "Content root for deployment: $contentRoot"

# 7. Create pre-update backup of existing files and record pre-existing files manifest
$backupDir = Join-Path ([System.IO.Path]::GetTempPath()) ("xenray_backup_" + [System.Guid]::NewGuid().ToString("N"))
Log "Creating pre-update backup of existing installation in: $backupDir"
try {
    $preExistingFiles = New-XenrayBackupManifest -AppDir $AppDir -BackupDir $backupDir -ContentRoot $contentRoot
    Log "Pre-update backup completed ($($preExistingFiles.Count) pre-existing files tracked in manifest)."
} catch {
    Log "WARNING: Failed to create full pre-update backup: $_"
    $preExistingFiles = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
}

# 8. Copy extracted files over AppDir with retry
Log "Deploying updated files to $AppDir..."
$maxRetries = 5
$copySuccess = $false

for ($attempt = 1; $attempt -le $maxRetries; $attempt++) {
    try {
        if (-not (Test-Path -LiteralPath $AppDir)) {
            New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
        }

        Get-ChildItem -LiteralPath $contentRoot | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $AppDir -Recurse -Force -ErrorAction Stop
        }
        $copySuccess = $true
        Log "Files deployed successfully on attempt $attempt."
        break
    } catch {
        Log "Attempt $attempt failed to copy files: $_"
        Stop-XenrayProcessesInsideAppDir -TargetAppDir $AppDir
        Start-Sleep -Seconds 1
    }
}

# 9. Handle deployment failure with bounded rollback and cleanup of newly introduced files
if (-not $copySuccess) {
    [void](Invoke-XenrayDeploymentFailure -AppDir $AppDir -BackupDir $backupDir -ContentRoot $contentRoot -PreExistingFiles $preExistingFiles -SuppressDialog:$SuppressDialog)
    exit 1
}

# 10. Clean up staging directory, backup directory, and ZIP archive
try {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    Log "Cleaned up temporary staging and backup files."
} catch {}

# 11. Determine target executable and launch updated app
$targetExe = $ExePath
if (-not (Test-Path -LiteralPath $targetExe)) {
    $fallbackExe = Join-Path $AppDir "XenRay.exe"
    if (Test-Path -LiteralPath $fallbackExe) {
        $targetExe = $fallbackExe
    }
}

if (Test-Path -LiteralPath $targetExe) {
    Log "Launching updated application: $targetExe"
    Start-Process -FilePath $targetExe -WorkingDirectory $AppDir
    Log "Update completed successfully!"
} else {
    Log "WARNING: Could not find executable at $targetExe to restart."
    [System.Windows.Forms.MessageBox]::Show("Update completed, but XenRay could not be restarted automatically. Please start it manually from $AppDir.", "XenRay Update", 0, 64)
}

# 12. Self cleanup
Start-Sleep -Seconds 1
$launcherScript = Join-Path ([System.IO.Path]::GetTempPath()) "xenray_update_launcher.ps1"
if (Test-Path -LiteralPath $launcherScript) {
    Remove-Item -LiteralPath $launcherScript -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""


class AppUpdateService:
    """Manages application updates from GitHub releases."""

    @staticmethod
    def get_current_version() -> str:
        """
        Get the current app version.

        Returns:
            Version string (e.g., "0.1.5-alpha")
        """
        return APP_VERSION

    @staticmethod
    def parse_version(version_str: str) -> str:
        """
        Normalize version string by removing 'v' prefix.

        Args:
            version_str: Version string (e.g., "v1.0.0" or "1.0.0")

        Returns:
            Normalized version string without 'v' prefix
        """
        return version_str.lstrip("v")

    @staticmethod
    def compare_versions(current: str, latest: str) -> bool:
        """
        Compare two version strings.

        Args:
            current: Current version
            latest: Latest version

        Returns:
            True if latest is newer than current
        """
        # Normalize versions (remove 'v' prefix)
        current_normalized = AppUpdateService.parse_version(current)
        latest_normalized = AppUpdateService.parse_version(latest)

        try:
            from packaging import version

            return version.parse(latest_normalized) > version.parse(current_normalized)
        except Exception:
            # Fallback: simple string comparison (only if versions are different)
            # This is not ideal but prevents false positives
            logger.warning(f"Failed to compare versions properly: {current} vs {latest}")
            return current_normalized != latest_normalized

    @staticmethod
    def check_for_updates(include_prerelease: bool = False) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Check for updates via GitHub API.

        Args:
            include_prerelease: Whether to include pre-releases when querying releases.

        Returns:
            Tuple of (update_available, current_version, latest_version, download_url)
        """
        current_version = AppUpdateService.get_current_version()

        try:
            logger.info(
                f"Checking for updates... Current version: {current_version} (include_prerelease={include_prerelease})"
            )

            # Query GitHub API
            if include_prerelease:
                url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data_list = response.json()
                if not data_list or not isinstance(data_list, list):
                    return False, current_version, None, None
                data = data_list[0]
            else:
                response = requests.get(GITHUB_API_URL, timeout=10)
                response.raise_for_status()
                data = response.json()

            tag_name = data.get("tag_name", "")
            latest_version = AppUpdateService.parse_version(tag_name)

            # Find the appropriate asset for this platform
            download_url = AppUpdateService._find_asset_url(data.get("assets", []))

            if not download_url:
                logger.warning("No compatible asset found in release")
                return False, current_version, latest_version, None

            # Check if update is available
            if AppUpdateService.compare_versions(current_version, latest_version):
                logger.info(f"Update available: {current_version} → {latest_version}")
                return True, current_version, latest_version, download_url

            logger.info("App is up to date")
            return False, current_version, latest_version, download_url

        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
            return False, current_version, None, None

    @staticmethod
    def _find_asset_url(assets: list) -> Optional[str]:
        """
        Find the download URL for the appropriate platform asset.

        Args:
            assets: List of asset objects from GitHub API

        Returns:
            Download URL or None
        """
        platform = PlatformUtils.get_platform()
        arch = PlatformUtils.get_architecture()

        # Determine asset name pattern
        if platform == "windows":
            if arch == "x86_64":
                pattern = "windows-x64.zip"
            else:
                pattern = "windows-x86.zip"
        elif platform == "linux":
            pattern = "linux.AppImage"  # Future support
        elif platform == "macos":
            pattern = "macos.dmg"  # Future support
        else:
            return None

        # Find matching asset
        for asset in assets:
            name = asset.get("name", "")
            if pattern in name.lower():
                return asset.get("browser_download_url")

        return None

    @staticmethod
    def download_update(url: str, progress_callback: Optional[Callable[[int], None]] = None) -> Optional[str]:
        """
        Download update ZIP file.

        Args:
            url: Download URL
            progress_callback: Function to report progress (0-100)

        Returns:
            Path to downloaded file, or None on failure
        """
        try:
            logger.info(f"Downloading update from: {url}")

            # Download to temp directory
            zip_path = os.path.join(tempfile.gettempdir(), "xenray_update.zip")

            # Stream download with progress
            response = requests.get(url, stream=True, timeout=UPDATE_DOWNLOAD_TIMEOUT)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            if total_size < UPDATE_MIN_FILE_SIZE:
                logger.error(f"Downloaded file too small: {total_size} bytes")
                return None

            downloaded_size = 0
            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if progress_callback and total_size > 0:
                            progress = int((downloaded_size / total_size) * 100)
                            progress_callback(progress)

            # Verify download
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) < UPDATE_MIN_FILE_SIZE:
                logger.error("Downloaded file validation failed")
                return None

            # SHA-256 verification when a .dgst sidecar is published.
            if not AppUpdateService._verify_app_sha256(zip_path, url):
                return None

            logger.info(f"Download complete: {zip_path}")
            return zip_path

        except Exception as e:
            logger.error(f"Failed to download update: {e}")
            return None

    @staticmethod
    def create_updater_script(zip_path: str, app_dir: str) -> Optional[str]:
        """
        Create PowerShell updater script.

        The script will:
        1. Wait for main process to exit
        2. Extract ZIP to app directory
        3. Restart the app
        4. Delete itself

        Args:
            zip_path: Path to downloaded ZIP
            app_dir: Application directory

        Returns:
            Path to updater script copy, or None on failure
        """
        try:
            # Get current process ID
            pid = os.getpid()

            # Log mode and paths for debugging
            is_frozen = getattr(sys, "frozen", False)
            logger.info(f"[AppUpdate] Running in {'EXE' if is_frozen else 'DEV'} mode")
            logger.info(f"[AppUpdate] sys.executable: {sys.executable}")
            logger.info(f"[AppUpdate] app_dir: {app_dir}")
            logger.info(f"[AppUpdate] zip_path: {zip_path}")
            logger.info(f"[AppUpdate] PID: {pid}")

            # Determine executable path
            if is_frozen:
                exe_path = sys.executable
                # A PyInstaller one-file build keeps the real EXE at
                # sys.executable; never point at a temp _MEI extraction dir.
                if not exe_path.lower().endswith(".exe"):
                    if sys.argv and sys.argv[0].lower().endswith(".exe"):
                        exe_path = os.path.abspath(sys.argv[0])
                logger.info(f"[AppUpdate] EXE path (frozen): {exe_path}")
            else:
                # Development mode - use poetry run
                exe_path = os.path.join(app_dir, "XenRay.exe")
                logger.info(f"[AppUpdate] EXE path (dev): {exe_path}")

            # Find the updater script template
            script_template = None
            if is_frozen:
                candidates = [
                    os.path.join(os.path.dirname(sys.executable), "scripts", "xenray_updater.ps1"),
                    os.path.join(getattr(sys, "_MEIPASS", ""), "scripts", "xenray_updater.ps1"),
                    os.path.join(os.path.dirname(sys.executable), "xenray_updater.ps1"),
                ]
                for c in candidates:
                    if c and os.path.exists(c):
                        script_template = c
                        break
                logger.info(f"[AppUpdate] Looking for script in EXE candidates: {script_template}")
            else:
                # Running from source — project root is 4 levels up
                project_root = Path(__file__).resolve().parents[3]
                candidate = os.path.join(project_root, "scripts", "xenray_updater.ps1")
                if os.path.exists(candidate):
                    script_template = candidate
                logger.info(f"[AppUpdate] Looking for script in source dir: {script_template}")

            script_copy = os.path.join(tempfile.gettempdir(), "xenray_updater_run.ps1")
            if script_template and os.path.exists(script_template):
                shutil.copy(script_template, script_copy)
                logger.info(f"[AppUpdate] Copied template script to: {script_copy}")
            else:
                logger.info(f"[AppUpdate] Template not on disk; generating self-contained updater at {script_copy}")
                with open(script_copy, "w", encoding="utf-8") as f:
                    f.write(AppUpdateService.get_embedded_updater_script())

            # Create wrapper script that calls the main script with parameters
            safe_app_dir = app_dir.rstrip("\\/")
            safe_exe_path = exe_path.rstrip("\\/")
            wrapper_path = os.path.join(tempfile.gettempdir(), "xenray_update_launcher.ps1")
            wrapper_content = f"""
# XenRay Update Launcher
& "{script_copy}" -ProcessID {pid} -ZipPath "{zip_path}" -AppDir "{safe_app_dir}" -ExePath "{safe_exe_path}"
"""

            with open(wrapper_path, "w", encoding="utf-8") as f:
                f.write(wrapper_content)

            logger.info(f"[AppUpdate] Created wrapper script: {wrapper_path}")
            logger.info(f"[AppUpdate] Wrapper content:\n{wrapper_content}")
            return wrapper_path

        except Exception as e:
            logger.error(f"Failed to create updater script: {e}")
            return None

    @staticmethod
    def get_embedded_updater_script() -> str:
        """Return fallback content for xenray_updater.ps1 if template not found on disk."""
        try:
            candidates = [
                Path(__file__).resolve().parents[3] / "scripts" / "xenray_updater.ps1",
                Path(sys.executable).parent / "scripts" / "xenray_updater.ps1",
                Path(getattr(sys, "_MEIPASS", "")) / "scripts" / "xenray_updater.ps1",
            ]
            for c in candidates:
                if c.is_file():
                    return c.read_text(encoding="utf-8")
        except Exception:
            pass

        return _EMBEDDED_UPDATER_SCRIPT

    # ---- SHA-256 verification -------------------------------------------

    @staticmethod
    def _verify_app_sha256(file_path: str, download_url: str) -> bool:
        """Verify downloaded update ZIP against .dgst sidecar (if published).

        When the release doesn't include a .dgst file the check is skipped
        gracefully — backward-compatible with existing releases.
        """
        dgst_url = download_url + ".dgst"
        expected = None
        try:
            resp = requests.get(dgst_url, timeout=15)
            if resp.status_code == 404:
                logger.info(f"[AppUpdate] No .dgst at {dgst_url} — skipping SHA-256 check")
                return True
            resp.raise_for_status()
            for line in resp.text.splitlines():
                if line.startswith("SHA2-256="):
                    val = line.split("=", 1)[1].strip().lower()
                    if val and all(c in "0123456789abcdef" for c in val) and len(val) >= 32:
                        expected = val
                    break
            else:
                expected = "MALFORMED"
        except Exception as e:
            logger.warning(f"[AppUpdate] Could not fetch .dgst sidecar: {e}")
            return True  # network hiccup on sidecar — don't block update

        if expected == "MALFORMED":
            logger.error(
                f"[AppUpdate] Sidecar at {dgst_url} returned malformed content or no valid SHA2-256. Discarding update."
            )
            try:
                os.remove(file_path)
            except OSError:
                pass
            return False

        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 16), b""):
                    h.update(chunk)
            actual = h.hexdigest()
        except OSError as e:
            logger.error(f"[AppUpdate] SHA-256 read error: {e}")
            return False

        if actual != expected:
            logger.error(
                f"[AppUpdate] SHA-256 MISMATCH — expected {expected}, got {actual}. "
                "Update ZIP is corrupted or tampered — discarding."
            )
            try:
                os.remove(file_path)
            except OSError:
                pass
            return False

        logger.info(f"[AppUpdate] SHA-256 verified: {actual[:16]}…")
        return True

    @staticmethod
    def apply_update(zip_path: str, disconnect_callback: Optional[Callable[[], None]] = None) -> bool:
        """
        Apply the update by launching updater script.

        Args:
            zip_path: Path to downloaded ZIP
            disconnect_callback: Optional callable to disconnect active VPN

        Returns:
            True if updater was launched successfully
        """
        try:
            # 1. Cleanly disconnect VPN to restore system network routing / DNS
            if disconnect_callback:
                try:
                    logger.info("[AppUpdate] Invoking provided disconnect callback...")
                    disconnect_callback()
                except Exception as e:
                    logger.warning(f"[AppUpdate] Disconnect callback failed: {e}")
            else:
                try:
                    from src.core.container import get_connection_manager

                    cm = get_connection_manager()
                    if cm and getattr(cm, "is_connected", False):
                        logger.info("[AppUpdate] Disconnecting active VPN session before updating...")
                        cm.disconnect()
                except Exception as e:
                    logger.warning(f"[AppUpdate] Error disconnecting VPN before update: {e}")

            # 2. Terminate all core engine instances (xray, sing-box) to release file handles
            try:
                from src.services.core_engines.xray_process_manager import XrayProcessManager

                XrayProcessManager.kill_all_core_instances()
            except Exception as e:
                logger.warning(f"[AppUpdate] Error stopping Xray instances: {e}")

            try:
                from src.services.core_engines.singbox_process_manager import SingboxProcessManager

                SingboxProcessManager.kill_all_core_instances()
            except Exception as e:
                logger.warning(f"[AppUpdate] Error stopping Singbox instances: {e}")

            # Get app directory
            if getattr(sys, "frozen", False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = str(Path(__file__).resolve().parents[3])

            logger.info(f"Applying update to: {app_dir}")

            # Create updater script
            script_path = AppUpdateService.create_updater_script(zip_path, app_dir)
            if not script_path:
                return False

            # Launch updater script as detached process
            # Use START command for reliable detached launch on Windows
            cmd = f'start "" powershell.exe -ExecutionPolicy Bypass -File "{script_path}"'
            subprocess.Popen(
                cmd,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            logger.info("Updater script launched successfully")

            # Schedule clean exit so UI thread has time to render "Restarting..."
            def _deferred_exit():
                import time

                time.sleep(1.5)
                try:
                    from src.utils.process_utils import ProcessUtils

                    ProcessUtils.kill_process_tree()
                except Exception:
                    pass
                os._exit(0)

            threading.Thread(target=_deferred_exit, daemon=True).start()
            return True

        except Exception as e:
            logger.error(f"Failed to apply update: {e}")
            return False
