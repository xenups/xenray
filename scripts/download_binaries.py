#!/usr/bin/env python3
"""
Download Xray and Singbox binaries for Windows from GitHub releases.

This script:
1. Reads versions from .env file
2. Downloads from official GitHub releases
3. Extracts to bin/ folder
4. Supports both 32-bit and 64-bit architectures
5. Ensures Windows 7+ compatibility

Usage:
    python scripts/download_binaries.py
    python scripts/download_binaries.py --arch 32
"""

import os
import sys
import zipfile
import urllib.request
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Configuration
BIN_DIR = PROJECT_ROOT / "bin"
TEMP_DIR = PROJECT_ROOT / "temp_downloads"

# GitHub release URLs
XRAY_URL_TEMPLATE = "https://github.com/XTLS/Xray-core/releases/download/v{version}/Xray-windows-{arch}.zip"
SINGBOX_URL_TEMPLATE = "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-windows-amd{arch}.zip"


def get_config(arch: int = 64):
    """Get configuration from environment."""
    xray_version = os.getenv("XRAY_VERSION", "1.8.24")
    singbox_version = os.getenv("SINGBOX_VERSION", "1.10.6")
    
    return {
        "xray_version": xray_version,
        "singbox_version": singbox_version,
        "arch": arch,
        "xray_url": XRAY_URL_TEMPLATE.format(version=xray_version, arch=arch),
        "singbox_url": SINGBOX_URL_TEMPLATE.format(version=singbox_version, arch=arch),
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


def extract_zip(zip_path: Path, extract_dir: Path, executable_name: str):
    """Extract specific executable from zip."""
    print(f"  [EXTRACT] {zip_path.name}")
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        # Find the executable
        exe_found = False
        for file in z.namelist():
            if file.endswith(executable_name):
                # Extract to bin directory
                z.extract(file, extract_dir)
                
                # Move to root of bin if nested
                extracted_path = extract_dir / file
                final_path = extract_dir / executable_name
                
                if extracted_path != final_path:
                    extracted_path.replace(final_path)
                
                print(f"  [OK] Extracted {executable_name}")
                exe_found = True
                break
        
        if not exe_found:
            print(f"  [WARNING] {executable_name} not found in archive!")


def cleanup(temp_dir: Path):
    """Remove temporary files."""
    import shutil
    if temp_dir.exists():
        print(f"\n[CLEANUP] Removing {temp_dir}")
        shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(description="Download Xray and Singbox binaries")
    parser.add_argument("--arch", type=int, choices=[32, 64], default=64,
                       help="Architecture: 32 or 64 (default: 64)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Downloading Xray and Singbox Binaries")
    print("=" * 60)
    
    # Get configuration
    config = get_config(args.arch)
    
    print(f"\nConfiguration:")
    print(f"  Xray Version: {config['xray_version']}")
    print(f"  Singbox Version: {config['singbox_version']}")
    print(f"  Architecture: {config['arch']}-bit")
    
    # Create directories
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        # Download Xray
        print("\n[STEP 1] Downloading Xray...")
        xray_zip = TEMP_DIR / f"xray-{config['xray_version']}.zip"
        download_file(config["xray_url"], xray_zip)
        extract_zip(xray_zip, BIN_DIR, "xray.exe")
        
        # Download Singbox
        print("\n[STEP 2] Downloading Singbox...")
        singbox_zip = TEMP_DIR / f"singbox-{config['singbox_version']}.zip"
        download_file(config["singbox_url"], singbox_zip)
        extract_zip(singbox_zip, BIN_DIR, "sing-box.exe")
        
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
