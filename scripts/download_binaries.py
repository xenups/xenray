#!/usr/bin/env python3
"""
Download Xray and Singbox binaries from GitHub releases.

This script:
1. Reads versions from .env file
2. Downloads from official GitHub releases
3. Extracts to bin/ folder with platform-specific subdirectories
4. Supports Windows (32/64-bit) and Linux (x86_64/arm64)
5. Sets executable permissions on Linux/macOS

Usage:
    python scripts/download_binaries.py                    # Auto-detect platform
    python scripts/download_binaries.py --platform linux   # Force Linux
    python scripts/download_binaries.py --platform windows --arch 32
"""

import argparse
import os
import platform
import shutil
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment
load_dotenv(PROJECT_ROOT / ".env")

# Configuration
TEMP_DIR = PROJECT_ROOT / "temp_downloads"

# GitHub release URLs - Windows
XRAY_WINDOWS_URL = "https://github.com/XTLS/Xray-core/releases/download/v{version}/Xray-windows-{arch}.zip"
SINGBOX_WINDOWS_URL = (
    "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-windows-amd{arch}.zip"
)

# GitHub release URLs - Linux
XRAY_LINUX_X64_URL = "https://github.com/XTLS/Xray-core/releases/download/v{version}/Xray-linux-64.zip"
XRAY_LINUX_ARM64_URL = "https://github.com/XTLS/Xray-core/releases/download/v{version}/Xray-linux-arm64-v8a.zip"
SINGBOX_LINUX_X64_URL = (
    "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-linux-amd64.tar.gz"
)
SINGBOX_LINUX_ARM64_URL = (
    "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-linux-arm64.tar.gz"
)


def detect_platform() -> str:
    """Detect current platform."""
    system = platform.system().lower()
    if system == "windows" or os.name == "nt":
        return "windows"
    elif system == "darwin":
        return "macos"
    else:
        return "linux"


def detect_architecture() -> str:
    """Detect CPU architecture."""
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        return "x86_64"
    elif machine in ("arm64", "aarch64", "arm64-v8a"):
        return "arm64"
    elif machine in ("i386", "i686", "x86"):
        return "x86"
    return "x86_64"  # Default


def get_config(target_platform: str, arch: str):
    """Get configuration from environment."""
    xray_version = os.getenv("XRAY_VERSION", "25.12.8")
    singbox_version = os.getenv("SINGBOX_VERSION", "1.12.14")

    # Determine bin directory based on platform
    if target_platform == "windows":
        bin_dir = PROJECT_ROOT / "bin"
        xray_url = XRAY_WINDOWS_URL.format(version=xray_version, arch=arch)
        singbox_url = SINGBOX_WINDOWS_URL.format(version=singbox_version, arch=arch)
        xray_exe = "xray.exe"
        singbox_exe = "sing-box.exe"
    elif target_platform == "linux":
        # Platform-specific bin directory
        arch_dir = "linux-x86_64" if arch == "x86_64" else "linux-arm64"
        bin_dir = PROJECT_ROOT / "bin" / arch_dir
        
        if arch == "arm64":
            xray_url = XRAY_LINUX_ARM64_URL.format(version=xray_version)
            singbox_url = SINGBOX_LINUX_ARM64_URL.format(version=singbox_version)
        else:
            xray_url = XRAY_LINUX_X64_URL.format(version=xray_version)
            singbox_url = SINGBOX_LINUX_X64_URL.format(version=singbox_version)
        xray_exe = "xray"
        singbox_exe = "sing-box"
    else:
        raise ValueError(f"Unsupported platform: {target_platform}")

    return {
        "xray_version": xray_version,
        "singbox_version": singbox_version,
        "platform": target_platform,
        "arch": arch,
        "bin_dir": bin_dir,
        "xray_url": xray_url,
        "singbox_url": singbox_url,
        "xray_exe": xray_exe,
        "singbox_exe": singbox_exe,
    }


def download_file(url: str, dest: Path) -> Path:
    """Download a file with progress."""
    print(f"  [DOWNLOAD] {url}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, (downloaded / total_size) * 100) if total_size > 0 else 0
        print(f"\r  Progress: {percent:.1f}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=progress)
    print()  # New line after progress
    print(f"  [OK] Downloaded to {dest}")
    return dest


def extract_zip(zip_path: Path, extract_dir: Path, executable_name: str, extra_files: list = None):
    """Extract executable and optional extra files from zip."""
    print(f"  [EXTRACT] {zip_path.name}")

    if extra_files is None:
        extra_files = []

    with zipfile.ZipFile(zip_path, "r") as z:
        # Find and extract the executable
        exe_found = False
        for file in z.namelist():
            if file.endswith(executable_name) or file == executable_name:
                # Extract to bin directory
                z.extract(file, extract_dir)

                # Move to root of bin if nested
                extracted_path = extract_dir / file
                final_path = extract_dir / executable_name

                if extracted_path != final_path:
                    extracted_path.replace(final_path)

                # Set executable permission on Unix
                if os.name != "nt":
                    st = os.stat(final_path)
                    os.chmod(final_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

                print(f"  [OK] Extracted {executable_name}")
                exe_found = True
                break

        if not exe_found:
            print(f"  [WARNING] {executable_name} not found in archive!")

        # Extract extra files (like geoip.dat, geosite.dat)
        for extra_file in extra_files:
            for file in z.namelist():
                if file.endswith(extra_file) or file == extra_file:
                    z.extract(file, extract_dir)
                    extracted_path = extract_dir / file
                    final_path = extract_dir / extra_file
                    if extracted_path != final_path:
                        extracted_path.replace(final_path)
                    print(f"  [OK] Extracted {extra_file}")
                    break


def extract_tarball(tar_path: Path, extract_dir: Path, executable_name: str):
    """Extract specific executable from tar.gz."""
    print(f"  [EXTRACT] {tar_path.name}")

    with tarfile.open(tar_path, "r:gz") as tar:
        # Find the executable
        exe_found = False
        for member in tar.getmembers():
            if member.name.endswith(executable_name) or os.path.basename(member.name) == executable_name:
                # Extract to temp location
                tar.extract(member, extract_dir)

                # Move to root of bin dir
                extracted_path = extract_dir / member.name
                final_path = extract_dir / executable_name

                if extracted_path != final_path:
                    shutil.move(str(extracted_path), str(final_path))
                    # Clean up nested directories
                    nested_dir = extract_dir / member.name.split("/")[0]
                    if nested_dir.exists() and nested_dir.is_dir():
                        shutil.rmtree(nested_dir, ignore_errors=True)

                # Set executable permission
                st = os.stat(final_path)
                os.chmod(final_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

                print(f"  [OK] Extracted {executable_name}")
                exe_found = True
                break

        if not exe_found:
            print(f"  [WARNING] {executable_name} not found in archive!")


def cleanup(temp_dir: Path):
    """Remove temporary files."""
    if temp_dir.exists():
        print(f"\n[CLEANUP] Removing {temp_dir}")
        shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(description="Download Xray and Singbox binaries")
    parser.add_argument(
        "--platform",
        type=str,
        choices=["windows", "linux"],
        default=None,
        help="Target platform (default: auto-detect)",
    )
    parser.add_argument(
        "--arch",
        type=str,
        choices=["32", "64", "x86_64", "arm64"],
        default=None,
        help="Architecture (default: auto-detect)",
    )
    args = parser.parse_args()

    # Auto-detect platform and architecture if not specified
    target_platform = args.platform or detect_platform()
    
    if args.arch:
        if args.arch in ("64", "x86_64"):
            arch = "x86_64"
        elif args.arch == "arm64":
            arch = "arm64"
        else:
            arch = args.arch  # "32" for Windows
    else:
        arch = detect_architecture()

    # For Windows, convert architecture to 32/64 format
    if target_platform == "windows":
        if arch in ("x86_64", "64"):
            arch = "64"
        elif arch in ("x86", "32"):
            arch = "32"
        else:
            arch = "64"

    print("=" * 60)
    print("Downloading Xray and Singbox Binaries")
    print("=" * 60)

    # Get configuration
    config = get_config(target_platform, arch)

    print(f"\nConfiguration:")
    print(f"  Xray Version: {config['xray_version']}")
    print(f"  Singbox Version: {config['singbox_version']}")
    print(f"  Platform: {config['platform']}")
    print(f"  Architecture: {config['arch']}")
    print(f"  Bin Directory: {config['bin_dir']}")

    # Create directories
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    config["bin_dir"].mkdir(parents=True, exist_ok=True)

    try:
        # Download Xray
        print("\n[STEP 1] Downloading Xray...")
        xray_ext = ".zip"  # Xray always uses zip
        xray_archive = TEMP_DIR / f"xray-{config['xray_version']}{xray_ext}"
        download_file(config["xray_url"], xray_archive)
        # Extract xray executable and geo data files
        extract_zip(
            xray_archive,
            config["bin_dir"],
            config["xray_exe"],
            extra_files=["geoip.dat", "geosite.dat"]
        )

        # Download Singbox
        print("\n[STEP 2] Downloading Singbox...")
        if target_platform == "linux":
            singbox_archive = TEMP_DIR / f"singbox-{config['singbox_version']}.tar.gz"
            download_file(config["singbox_url"], singbox_archive)
            extract_tarball(singbox_archive, config["bin_dir"], config["singbox_exe"])
        else:
            singbox_archive = TEMP_DIR / f"singbox-{config['singbox_version']}.zip"
            download_file(config["singbox_url"], singbox_archive)
            extract_zip(singbox_archive, config["bin_dir"], config["singbox_exe"])

        print("\n" + "=" * 60)
        print("DOWNLOAD COMPLETE!")
        print(f"Binaries location: {config['bin_dir']}")
        print("=" * 60)

        # List downloaded files
        print("\nDownloaded files:")
        for f in config["bin_dir"].iterdir():
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name}: {size_mb:.2f} MB")

    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cleanup(TEMP_DIR)

    return 0


if __name__ == "__main__":
    sys.exit(main())
