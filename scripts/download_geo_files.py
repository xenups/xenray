#!/usr/bin/env python3
"""
Download geo files (geoip.dat, geosite.dat) and wintun.dll to bin/ folder.

Geo files are from Chocolate4U/Iran-v2ray-rules for Iranian-optimized routing.
wintun.dll is required by Xray for TUN interface on Windows.

These files are bundled in CI releases so users don't need to download
them on first start.

Usage:
    python scripts/download_geo_files.py
"""

import os
import sys
import urllib.request
import zipfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Output directory - use bin/ folder where xray.exe is located
BIN_DIR = PROJECT_ROOT / "bin"

# GitHub URLs — Chocolate4U/Iran-v2ray-rules provides geo files with
# Iranian-specific routing entries (IR geoip/geosite)
GEOIP_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geoip.dat"
GEOSITE_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geosite.dat"

# wintun.dll is required for Xray TUN interface on Windows
WINTUN_URL = "https://www.wintun.net/builds/wintun-0.14.1.zip"
WINTUN_FILE = "wintun.dll"


def download_file(url: str, dest: Path) -> Path:
    """Download a file with progress."""
    if dest.exists():
        print(f"  [SKIP] {dest.name} already exists")
        return dest

    print(f"  [DOWNLOAD] {url}")

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, (downloaded / total_size) * 100) if total_size > 0 else 0
        print(f"\r  Progress: {percent:.1f}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=progress)
    print()
    print(f"  [OK] Downloaded to {dest}")
    return dest


def download_geo_files():
    """Download both geoip.dat and geosite.dat."""
    print("\n[STEP 1] Downloading geoip.dat...")
    download_file(GEOIP_URL, BIN_DIR / "geoip.dat")

    print("\n[STEP 2] Downloading geosite.dat...")
    download_file(GEOSITE_URL, BIN_DIR / "geosite.dat")


def download_wintun():
    """
    Download wintun.dll and extract it to bin/.
    wintun.dll is architecture-specific — we extract the amd64 variant.
    """
    print("\n[STEP 3] Downloading and extracting wintun.dll...")

    zip_path = BIN_DIR / "wintun.zip"
    download_file(WINTUN_URL, zip_path)

    target = BIN_DIR / WINTUN_FILE
    if target.exists():
        print(f"  [SKIP] {WINTUN_FILE} already exists")
        zip_path.unlink(missing_ok=True)
        return

    with zipfile.ZipFile(zip_path, "r") as z:
        # wintun zip contains: wintun/bin/amd64/wintun.dll
        arch = "arm64" if os.environ.get("PROCESSOR_ARCHITECTURE", "").startswith("ARM") else "amd64"
        member = f"wintun/bin/{arch}/wintun.dll"
        if member in z.namelist():
            z.extract(member, BIN_DIR)
            extracted = BIN_DIR / member
            extracted.replace(target)
            # Clean up nested dirs (deepest first)
            for p in [BIN_DIR / f"wintun/bin/{arch}", BIN_DIR / "wintun/bin", BIN_DIR / "wintun"]:
                p.rmdir() if p.exists() else None
            print(f"  [OK] Extracted {WINTUN_FILE} ({arch})")
        else:
            # Fallback: try any wintun.dll in the zip
            for name in z.namelist():
                if name.endswith("wintun.dll"):
                    z.extract(name, BIN_DIR)
                    extracted = BIN_DIR / name
                    extracted.replace(target)
                    # Clean up any extracted dirs
                    parent = BIN_DIR / name.rsplit("/", 1)[0]
                    while parent != BIN_DIR:
                        parent.rmdir()
                        parent = parent.parent
                    print(f"  [OK] Extracted {WINTUN_FILE} from {name}")
                    break
            else:
                print(f"  [WARNING] wintun.dll not found in archive!")

    zip_path.unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("Downloading Geo Files and wintun.dll to bin/")
    print("=" * 60)

    BIN_DIR.mkdir(parents=True, exist_ok=True)

    try:
        download_geo_files()
        download_wintun()

        print("\n" + "=" * 60)
        print("DOWNLOAD COMPLETE!")
        print(f"Files location: {BIN_DIR}")
        for f in ["geoip.dat", "geosite.dat", "wintun.dll"]:
            p = BIN_DIR / f
            size = p.stat().st_size / 1024 / 1024 if p.exists() else 0
            print(f"  {f}: {'[OK]' if p.exists() else '[FAIL]'} ({size:.1f} MB)")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
