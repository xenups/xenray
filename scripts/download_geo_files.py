#!/usr/bin/env python3
"""
Download geo files (geoip.dat, geosite.dat) from Chocolate4U/Iran-v2ray-rules
for Iranian-optimized routing and wintun.dll driver.

By default, downloads geoip.dat and geosite.dat directly into assets/rules/
where Xenray runtime and XRAY_LOCATION_ASSET expect them.

Usage:
    python scripts/download_geo_files.py
    python scripts/download_geo_files.py --force
    python scripts/download_geo_files.py --dest assets/rules --force
"""

import argparse
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default directories
RULES_DIR = PROJECT_ROOT / "assets" / "rules"
BIN_DIR = PROJECT_ROOT / "bin"

# GitHub URLs — Chocolate4U/Iran-v2ray-rules provides geo files with
# Iranian-specific routing entries (IR geoip/geosite)
GEOIP_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geoip.dat"
GEOSITE_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geosite.dat"

# wintun.dll is required for Xray TUN interface on Windows
WINTUN_URL = "https://www.wintun.net/builds/wintun-0.14.1.zip"
WINTUN_FILE = "wintun.dll"

# Minimum sane file size for .dat files (~1MB; geoip ~16MB, geosite ~7MB)
MIN_DAT_SIZE = 1024 * 1024


def download_file(
    url: str,
    dest: Path,
    force: bool = False,
    min_size: int = MIN_DAT_SIZE,
) -> Path:
    """Download a file atomically with progress and minimum size validation."""
    if dest.exists() and not force:
        print(f"  [SKIP] {dest.name} already exists (use --force to overwrite)")
        return dest

    print(f"  [DOWNLOAD] {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_name(f"{dest.name}.tmp")

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, (downloaded / total_size) * 100) if total_size > 0 else 0
        print(f"\r  Progress: {percent:.1f}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, tmp_dest, reporthook=progress)
        print()

        actual_size = tmp_dest.stat().st_size
        if actual_size < min_size:
            tmp_dest.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded file too small: {actual_size} bytes (min: {min_size})")

        # Atomic replace
        tmp_dest.replace(dest)
        print(f"  [OK] Saved to {dest} ({actual_size / 1024 / 1024:.2f} MB)")
        return dest
    except Exception:
        tmp_dest.unlink(missing_ok=True)
        raise


def download_geo_files(dest_dir: Path = RULES_DIR, force: bool = False):
    """Download both geoip.dat and geosite.dat into the specified directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    print("\n[STEP 1] Downloading geoip.dat...")
    download_file(GEOIP_URL, dest_dir / "geoip.dat", force=force, min_size=MIN_DAT_SIZE)

    print("\n[STEP 2] Downloading geosite.dat...")
    download_file(GEOSITE_URL, dest_dir / "geosite.dat", force=force, min_size=MIN_DAT_SIZE)


def download_wintun(dest_dir: Path = BIN_DIR, force: bool = False):
    """
    Download wintun.dll and extract it to destination bin directory.
    wintun.dll is architecture-specific — extracts the amd64 variant.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / WINTUN_FILE
    if target.exists() and not force:
        print(f"  [SKIP] {WINTUN_FILE} already exists")
        return

    print("\n[STEP 3] Downloading and extracting wintun.dll...")
    zip_path = dest_dir / "wintun.zip"
    download_file(WINTUN_URL, zip_path, force=True, min_size=1024)

    with zipfile.ZipFile(zip_path, "r") as z:
        # wintun zip contains: wintun/bin/amd64/wintun.dll
        arch = "arm64" if os.environ.get("PROCESSOR_ARCHITECTURE", "").startswith("ARM") else "amd64"
        member = f"wintun/bin/{arch}/wintun.dll"
        if member in z.namelist():
            z.extract(member, dest_dir)
            extracted = dest_dir / member
            extracted.replace(target)
            # Clean up nested dirs (deepest first)
            for p in [dest_dir / f"wintun/bin/{arch}", dest_dir / "wintun/bin", dest_dir / "wintun"]:
                p.rmdir() if p.exists() else None
            print(f"  [OK] Extracted {WINTUN_FILE} ({arch})")
        else:
            # Fallback: try any wintun.dll in the zip
            for name in z.namelist():
                if name.endswith("wintun.dll"):
                    z.extract(name, dest_dir)
                    extracted = dest_dir / name
                    extracted.replace(target)
                    parent = dest_dir / name.rsplit("/", 1)[0]
                    while parent != dest_dir:
                        parent.rmdir()
                        parent = parent.parent
                    print(f"  [OK] Extracted {WINTUN_FILE} from {name}")
                    break
            else:
                print("  [WARNING] wintun.dll not found in archive!")

    zip_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Download Xray Iran geo files (geoip.dat, geosite.dat) and wintun.dll")
    parser.add_argument(
        "--dest",
        type=Path,
        default=RULES_DIR,
        help="Destination directory for geo files (default: assets/rules)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force download and overwrite existing files",
    )
    parser.add_argument(
        "--with-wintun",
        action="store_true",
        default=False,
        help="Also download wintun.dll to bin/ directory",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"Downloading Iran Geo Files to {args.dest}")
    print("=" * 60)

    try:
        download_geo_files(dest_dir=args.dest, force=args.force)

        if args.with_wintun or not (BIN_DIR / WINTUN_FILE).exists():
            download_wintun(dest_dir=BIN_DIR, force=args.force)

        print("\n" + "=" * 60)
        print("DOWNLOAD COMPLETE!")
        print(f"Geo files location: {args.dest}")
        for f in ["geoip.dat", "geosite.dat"]:
            p = args.dest / f
            size = p.stat().st_size / 1024 / 1024 if p.exists() else 0
            print(f"  {f}: {'[OK]' if p.exists() else '[FAIL]'} ({size:.1f} MB)")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
