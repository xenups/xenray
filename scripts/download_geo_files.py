#!/usr/bin/env python3
"""
Download Xray geo files (geoip.dat and geosite.dat).

These files are required for Xray routing rules to work properly.

Usage:
    python scripts/download_geo_files.py
"""

import os
import sys
import urllib.request
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Output directory
ASSETS_DIR = PROJECT_ROOT / "assets"

# GitHub URLs for geo files
GEOIP_URL = "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
GEOSITE_URL = "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"


def download_file(url: str, dest: Path, rename_to: str = None) -> Path:
    """Download a file with progress."""
    final_dest = dest.parent / (rename_to or dest.name)
    
    if final_dest.exists():
        print(f"  [SKIP] {final_dest.name} already exists")
        return final_dest
    
    print(f"  [DOWNLOAD] {url}")
    
    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, (downloaded / total_size) * 100) if total_size > 0 else 0
        print(f"\r  Progress: {percent:.1f}%", end="", flush=True)
    
    urllib.request.urlretrieve(url, final_dest, reporthook=progress)
    print()  # New line after progress
    print(f"  [OK] Downloaded to {final_dest}")
    return final_dest


def main():
    print("=" * 60)
    print("Downloading Xray Geo Files")
    print("=" * 60)
    
    # Create assets directory
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        # Download geoip.dat
        print("\n[STEP 1] Downloading geoip.dat...")
        download_file(GEOIP_URL, ASSETS_DIR / "geoip.dat")
        
        # Download geosite.dat (renamed from dlc.dat)
        print("\n[STEP 2] Downloading geosite.dat...")
        download_file(GEOSITE_URL, ASSETS_DIR / "dlc.dat", rename_to="geosite.dat")
        
        print("\n" + "=" * 60)
        print("DOWNLOAD COMPLETE!")
        print(f"Files location: {ASSETS_DIR}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
