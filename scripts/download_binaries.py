#!/usr/bin/env python3
"""
Download Xray, Sing-box, and Wintun binaries for Windows from official releases.

This script:
1. Reads version numbers from .env file
2. Downloads Xray-core, Sing-box, and Wintun from official GitHub/Wintun releases
3. Extracts executables to bin/ folder
4. Supports both 32-bit and 64-bit architectures

Usage:
    python scripts/download_binaries.py
    python scripts/download_binaries.py --arch 32
"""

import argparse
import os
import sys
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
BIN_DIR = PROJECT_ROOT / "bin"
TEMP_DIR = PROJECT_ROOT / "temp_downloads"

# Architecture mappings
SINGBOX_ARCH_MAP = {64: "amd64", 32: "386"}
WINTUN_ARCH_MAP = {64: "amd64", 32: "x86"}

# GitHub / Official release URLs
XRAY_URL_TEMPLATE = "https://github.com/XTLS/Xray-core/releases/download/v{version}/Xray-windows-{arch}.zip"
SINGBOX_URL_TEMPLATE = (
    "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-windows-{sb_arch}.zip"
)
WINTUN_URL = "https://www.wintun.net/builds/wintun-0.14.1.zip"


def get_config(arch: int = 64):
    """Get configuration from environment."""
    xray_version = os.getenv("XRAY_VERSION", "26.7.28")
    singbox_version = os.getenv("SINGBOX_VERSION", "1.13.14")
    sb_arch = SINGBOX_ARCH_MAP.get(arch, "amd64")
    wintun_arch = WINTUN_ARCH_MAP.get(arch, "amd64")

    return {
        "xray_version": xray_version,
        "singbox_version": singbox_version,
        "arch": arch,
        "xray_url": XRAY_URL_TEMPLATE.format(version=xray_version, arch=arch),
        "singbox_url": SINGBOX_URL_TEMPLATE.format(version=singbox_version, sb_arch=sb_arch),
        "wintun_url": WINTUN_URL,
        "wintun_arch": wintun_arch,
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


def extract_zip(zip_path: Path, extract_dir: Path, target_filename: str, subpath_filter: str = None):
    """Extract specific executable or DLL from zip."""
    print(f"  [EXTRACT] {zip_path.name}")

    with zipfile.ZipFile(zip_path, "r") as z:
        file_found = False
        for file in z.namelist():
            if file.endswith(target_filename):
                if subpath_filter and subpath_filter not in file:
                    continue

                z.extract(file, extract_dir)

                extracted_path = extract_dir / file
                final_path = extract_dir / target_filename

                if extracted_path != final_path:
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    if final_path.exists():
                        final_path.unlink()
                    extracted_path.replace(final_path)
                    # Clean up nested directory created during zip extraction
                    import shutil

                    rel_parts = Path(file).parts
                    if len(rel_parts) > 1:
                        top_subfolder = extract_dir / rel_parts[0]
                        if top_subfolder.is_dir() and top_subfolder != extract_dir:
                            shutil.rmtree(top_subfolder, ignore_errors=True)

                print(f"  [OK] Extracted {target_filename}")
                file_found = True
                break

        if not file_found:
            print(f"  [WARNING] {target_filename} not found in archive {zip_path.name}!")


def cleanup(temp_dir: Path):
    """Remove temporary files."""
    import shutil

    if temp_dir.exists():
        print(f"\n[CLEANUP] Removing {temp_dir}")
        shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(description="Download Xray, Sing-box and Wintun binaries")
    parser.add_argument(
        "--arch",
        type=int,
        choices=[32, 64],
        default=64,
        help="Architecture: 32 or 64 (default: 64)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Downloading Core Binaries (Xray, Sing-box, Wintun)")
    print("=" * 60)

    config = get_config(args.arch)

    print("\nConfiguration:")
    print(f"  Xray Version: {config['xray_version']}")
    print(f"  Sing-box Version: {config['singbox_version']}")
    print(f"  Architecture: {config['arch']}-bit")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Download Xray
        print("\n[STEP 1] Downloading Xray...")
        xray_zip = TEMP_DIR / f"xray-{config['xray_version']}.zip"
        download_file(config["xray_url"], xray_zip)
        extract_zip(xray_zip, BIN_DIR, "xray.exe")

        # Step 2: Download Sing-box
        print("\n[STEP 2] Downloading Sing-box...")
        singbox_zip = TEMP_DIR / f"singbox-{config['singbox_version']}.zip"
        download_file(config["singbox_url"], singbox_zip)
        extract_zip(singbox_zip, BIN_DIR, "sing-box.exe")

        # Step 3: Download Wintun DLL if missing
        wintun_dll = BIN_DIR / "wintun.dll"
        if not wintun_dll.exists():
            print("\n[STEP 3] Downloading Wintun driver...")
            wintun_zip = TEMP_DIR / "wintun-0.14.1.zip"
            download_file(config["wintun_url"], wintun_zip)
            extract_zip(wintun_zip, BIN_DIR, "wintun.dll", subpath_filter=config["wintun_arch"])

        print("\n" + "=" * 60)
        print("DOWNLOAD COMPLETE!")
        print(f"Binaries location: {BIN_DIR}")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        return 1
    finally:
        cleanup(TEMP_DIR)

    return 0


if __name__ == "__main__":
    sys.exit(main())
