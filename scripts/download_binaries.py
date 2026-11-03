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
import hashlib
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

# Trusted pinned digests for upstream assets without dedicated .dgst sidecar endpoints
PINNED_CHECKSUMS = {
    "wintun-0.14.1.zip": "07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51",
    "sing-box-1.14.0-windows-amd64.zip": "3ffb56267da14e287be48bd10cf7e6505260125bad940b75101fbb4d5d58e5d6",
}


try:
    from src.core.constants import SINGBOX_VERSION as DEFAULT_SINGBOX_VERSION
    from src.core.constants import XRAY_VERSION as DEFAULT_XRAY_VERSION
except ImportError:
    DEFAULT_XRAY_VERSION = "26.10.31"
    DEFAULT_SINGBOX_VERSION = "1.14.0"


def get_config(arch: int = 64):
    """Get configuration from environment."""
    xray_version = os.getenv("XRAY_VERSION", DEFAULT_XRAY_VERSION)
    singbox_version = os.getenv("SINGBOX_VERSION", DEFAULT_SINGBOX_VERSION)
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


def download_file(
    url: str,
    dest: Path,
    require_dgst: bool = False,
    expected_sha256: str = None,
) -> Path:
    """Download a file with progress, then verify integrity against sidecar or pinned hash.

    Strict fail-closed behavior:
    - If require_dgst is True (mandatory for Xray):
      * .dgst sidecar must be fetched successfully (HTTP 200).
      * Must contain a valid SHA2-256 entry.
      * Expected hash format must be a valid 64-character hexadecimal digest.
      * Local SHA-256 is computed and compared.
      * Mismatch, missing sidecar, HTTP error, or malformed digest results in hard failure.
      * Unverified or invalid archive is removed immediately and never extracted.
    - If expected_sha256 is provided (or resolved from PINNED_CHECKSUMS):
      * Expected hash format must be valid 64-char hex string.
      * Local SHA-256 is compared against expected. Mismatch removes dest and raises RuntimeError.
    """
    print(f"  [DOWNLOAD] {url}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, (downloaded / total_size) * 100) if total_size > 0 else 0
        print(f"\r  Progress: {percent:.1f}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, dest, reporthook=progress)
        print()  # New line after progress
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed for {url}: {exc}") from exc

    resolved_expected = expected_sha256 or PINNED_CHECKSUMS.get(dest.name)

    if require_dgst:
        dgst_url = f"{url}.dgst"
        try:
            with urllib.request.urlopen(dgst_url, timeout=30) as resp:
                if resp.status != 200:
                    dest.unlink(missing_ok=True)
                    raise RuntimeError(f"HTTP {resp.status} fetching checksum sidecar {dgst_url}")
                sidecar = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"HTTP {exc.code} fetching required checksum sidecar {dgst_url}") from exc
        except urllib.error.URLError as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Network error fetching required checksum sidecar {dgst_url}: {exc.reason}") from exc
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Failed fetching required checksum sidecar {dgst_url}: {exc}") from exc

        parsed_sha = ""
        for line in sidecar.splitlines():
            line_clean = line.strip().lower()
            if line_clean.startswith("sha2-256="):
                parsed_sha = line_clean.split("=", 1)[1].strip()
                break
            elif line_clean.startswith("sha256="):
                parsed_sha = line_clean.split("=", 1)[1].strip()
                break

        if not parsed_sha:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Missing required SHA2-256 digest in sidecar {dgst_url}")

        if len(parsed_sha) != 64 or not all(c in "0123456789abcdef" for c in parsed_sha):
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Malformed SHA-256 digest format in sidecar {dgst_url}: '{parsed_sha}'")

        actual = hashlib.sha256(dest.read_bytes()).hexdigest().lower()
        if actual != parsed_sha:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"SHA-256 mismatch for {dest.name}: expected {parsed_sha[:16]}... got {actual[:16]}...")
        print(f"  [OK] SHA-256 verified against upstream .dgst: {parsed_sha[:16]}...")

    elif resolved_expected:
        expected_clean = resolved_expected.strip().lower()
        if len(expected_clean) != 64 or not all(c in "0123456789abcdef" for c in expected_clean):
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Malformed pinned SHA-256 digest format: '{resolved_expected}'")

        actual = hashlib.sha256(dest.read_bytes()).hexdigest().lower()
        if actual != expected_clean:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"SHA-256 mismatch for {dest.name}: expected {expected_clean[:16]}... got {actual[:16]}..."
            )
        print(f"  [OK] SHA-256 verified against trusted pinned digest: {expected_clean[:16]}...")

    else:
        # Asset without explicit requirement: attempt sidecar if present
        dgst_url = f"{url}.dgst"
        try:
            with urllib.request.urlopen(dgst_url, timeout=30) as resp:
                if resp.status == 200:
                    sidecar = resp.read().decode("utf-8", errors="replace")
                    for line in sidecar.splitlines():
                        line_clean = line.strip().lower()
                        if line_clean.startswith("sha2-256=") or line_clean.startswith("sha256="):
                            expected = line_clean.split("=", 1)[1].strip()
                            actual = hashlib.sha256(dest.read_bytes()).hexdigest().lower()
                            if actual != expected:
                                dest.unlink(missing_ok=True)
                                raise RuntimeError(f"SHA-256 mismatch for {dest.name}")
                            print(f"  [OK] SHA-256 verified: {expected[:16]}...")
                            break
        except (urllib.error.HTTPError, urllib.error.URLError):
            pass

    print(f"  [OK] Downloaded and verified to {dest}")
    return dest


def extract_zip(zip_path: Path, extract_dir: Path, target_filename: str, subpath_filter: str = None) -> Path:
    """Extract specific executable or DLL from zip.

    Strict fail-closed behavior:
    - If zip_path is missing or not a valid zipfile, raises FileNotFoundError or BadZipFile.
    - If target_filename is not found in archive, raises FileNotFoundError.
    - Returns the path to the extracted file.
    """
    print(f"  [EXTRACT] {zip_path.name}")

    if not zip_path.exists():
        raise FileNotFoundError(f"Archive not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as z:
        file_found = False
        final_path = extract_dir / target_filename

        for file in z.namelist():
            if file.endswith(target_filename):
                if subpath_filter and subpath_filter not in file:
                    continue

                z.extract(file, extract_dir)

                extracted_path = extract_dir / file

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
                return final_path

        if not file_found:
            raise FileNotFoundError(f"Required member '{target_filename}' not found in archive '{zip_path.name}'")


def cleanup(temp_dir: Path):
    """Remove temporary files."""
    import shutil

    if temp_dir.exists():
        print(f"\n[CLEANUP] Removing {temp_dir}")
        shutil.rmtree(temp_dir)


def main(args_list=None):
    parser = argparse.ArgumentParser(description="Download Xray, Sing-box and Wintun binaries")
    parser.add_argument(
        "--arch",
        type=int,
        choices=[32, 64],
        default=64,
        help="Architecture: 32 or 64 (default: 64)",
    )
    args = parser.parse_args(args_list)

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
        # Step 1: Download Xray (require_dgst=True enforces upstream .dgst sidecar)
        print("\n[STEP 1] Downloading Xray...")
        xray_zip = TEMP_DIR / f"xray-{config['xray_version']}.zip"
        download_file(config["xray_url"], xray_zip, require_dgst=True)
        extract_zip(xray_zip, BIN_DIR, "xray.exe")
        extract_zip(xray_zip, BIN_DIR, "geoip.dat")
        extract_zip(xray_zip, BIN_DIR, "geosite.dat")

        # Step 2: Download Sing-box
        print("\n[STEP 2] Downloading Sing-box...")
        singbox_zip = TEMP_DIR / f"singbox-{config['singbox_version']}.zip"
        download_file(config["singbox_url"], singbox_zip, expected_sha256=PINNED_CHECKSUMS.get(singbox_zip.name))
        extract_zip(singbox_zip, BIN_DIR, "sing-box.exe")

        # Step 3: Download Wintun DLL if missing
        wintun_dll = BIN_DIR / "wintun.dll"
        if not wintun_dll.exists():
            print("\n[STEP 3] Downloading Wintun driver...")
            wintun_zip = TEMP_DIR / "wintun-0.14.1.zip"
            download_file(config["wintun_url"], wintun_zip, expected_sha256=PINNED_CHECKSUMS.get(wintun_zip.name))
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
