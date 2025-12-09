#!/usr/bin/env python3
"""
Build script for creating a compact multilingual city database.

This script:
1. Downloads GeoNames cities500.txt and alternateNamesV2.txt
2. Filters cities by population (100k+)
3. Extracts multilingual names (en, fa, ru, zh)
4. Serializes with MessagePack and compresses with Zstandard

Output: assets/data/cities.msgpack.zst (< 5MB target)

Usage:
    python scripts/build_city_database.py
"""

import os
import sys
import zipfile
import urllib.request
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# GeoNames URLs
CITIES_URL = "https://download.geonames.org/export/dump/cities500.zip"
ALTERNATE_NAMES_URL = "https://download.geonames.org/export/dump/alternateNamesV2.zip"

# Output paths
DATA_DIR = PROJECT_ROOT / "assets" / "data"
OUTPUT_FILE = DATA_DIR / "cities.msgpack.zst"
TEMP_DIR = PROJECT_ROOT / "temp_geonames"

# Configuration
MIN_POPULATION = 100000  # Only cities with 100k+ population
TARGET_LANGUAGES = {"en", "fa", "ru", "zh"}


def download_file(url: str, dest: Path) -> Path:
    """Download a file if not already present."""
    if dest.exists():
        print(f"  [SKIP] {dest.name} already exists")
        return dest
    
    print(f"  [DOWNLOAD] {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"  [OK] Saved to {dest}")
    return dest


def extract_zip(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract a zip file and return list of extracted files."""
    print(f"  [EXTRACT] {zip_path.name}")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
        return [extract_dir / name for name in z.namelist()]


def parse_cities(cities_file: Path, min_pop: int) -> dict:
    """
    Parse cities500.txt and filter by population.
    
    Returns: {geonameid: {"name": english_name, "country": country_code}}
    """
    print(f"\n[STEP 2] Parsing cities (pop >= {min_pop:,})...")
    cities = {}
    
    with open(cities_file, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 15:
                continue
            
            geonameid = parts[0]
            name = parts[1]  # Main name (usually English or local)
            ascii_name = parts[2]
            country_code = parts[8]
            population = int(parts[14]) if parts[14] else 0
            
            if population >= min_pop:
                cities[geonameid] = {
                    "name": name,
                    "ascii": ascii_name,
                    "country": country_code,
                    "pop": population,
                }
    
    print(f"  [OK] Found {len(cities):,} cities with pop >= {min_pop:,}")
    return cities


def parse_alternate_names(alt_names_file: Path, city_ids: set, langs: set) -> dict:
    """
    Parse alternateNamesV2.txt for target languages.
    
    Returns: {geonameid: {"en": name, "fa": name, "ru": name, "zh": name}}
    """
    print(f"\n[STEP 3] Parsing alternate names for {langs}...")
    alt_names = defaultdict(dict)
    count = 0
    
    with open(alt_names_file, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue
            
            geonameid = parts[1]
            lang = parts[2]
            name = parts[3]
            
            # Only process cities we care about
            if geonameid not in city_ids:
                continue
            
            # Only process target languages
            if lang in langs:
                # Prefer non-historic, non-colloquial names
                is_preferred = len(parts) > 4 and parts[4] == "1"
                is_short = len(parts) > 5 and parts[5] == "1"
                
                # Store if no existing name or this is preferred
                if lang not in alt_names[geonameid] or is_preferred:
                    alt_names[geonameid][lang] = name
                    count += 1
    
    print(f"  [OK] Collected {count:,} alternate names")
    return dict(alt_names)


def build_database(cities: dict, alt_names: dict) -> dict:
    """
    Build the final database structure.
    
    Key: lowercase English/ASCII city name
    Value: {"en": ..., "fa": ..., "ru": ..., "zh": ...}
    """
    print("\n[STEP 4] Building database...")
    db = {}
    
    for geonameid, city_info in cities.items():
        # Get English name (from alternates or main name)
        names = alt_names.get(geonameid, {})
        en_name = names.get("en", city_info["name"])
        
        # Build entry
        entry = {
            "en": en_name,
            "fa": names.get("fa", en_name),
            "ru": names.get("ru", en_name),
            "zh": names.get("zh", en_name),
        }
        
        # Use lowercase ASCII name as key for lookup
        key = city_info["ascii"].lower()
        
        # Also add the English name as key if different
        en_key = en_name.lower()
        
        db[key] = entry
        if en_key != key:
            db[en_key] = entry
        
        # Also add the original name as key
        orig_key = city_info["name"].lower()
        if orig_key not in db:
            db[orig_key] = entry
    
    print(f"  [OK] Database has {len(db):,} entries")
    return db


def compress_database(db: dict, output_path: Path):
    """Serialize with MessagePack and compress with Zstandard."""
    import msgpack
    import zstandard as zstd
    
    print("\n[STEP 5] Compressing database...")
    
    # Serialize
    packed = msgpack.packb(db, use_bin_type=True)
    print(f"  MessagePack size: {len(packed):,} bytes ({len(packed)/1024/1024:.2f} MB)")
    
    # Compress with high compression level
    compressor = zstd.ZstdCompressor(level=19)  # Max compression
    compressed = compressor.compress(packed)
    print(f"  Zstd size: {len(compressed):,} bytes ({len(compressed)/1024/1024:.2f} MB)")
    
    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(compressed)
    
    print(f"  [OK] Saved to {output_path}")
    
    # Compression ratio
    ratio = len(packed) / len(compressed)
    print(f"  Compression ratio: {ratio:.1f}x")


def cleanup(temp_dir: Path):
    """Remove temporary files."""
    import shutil
    if temp_dir.exists():
        print(f"\n[CLEANUP] Removing {temp_dir}")
        shutil.rmtree(temp_dir)


def main():
    print("=" * 60)
    print("Building Multilingual City Database")
    print("=" * 60)
    
    # Create temp directory
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Download files
        print("\n[STEP 1] Downloading GeoNames data...")
        cities_zip = download_file(CITIES_URL, TEMP_DIR / "cities500.zip")
        alt_zip = download_file(ALTERNATE_NAMES_URL, TEMP_DIR / "alternateNamesV2.zip")
        
        # Extract
        extract_zip(cities_zip, TEMP_DIR)
        extract_zip(alt_zip, TEMP_DIR)
        
        cities_file = TEMP_DIR / "cities500.txt"
        alt_file = TEMP_DIR / "alternateNamesV2.txt"
        
        # Step 2: Parse cities
        cities = parse_cities(cities_file, MIN_POPULATION)
        city_ids = set(cities.keys())
        
        # Step 3: Parse alternate names
        alt_names = parse_alternate_names(alt_file, city_ids, TARGET_LANGUAGES)
        
        # Step 4: Build database
        db = build_database(cities, alt_names)
        
        # Step 5: Compress and save
        compress_database(db, OUTPUT_FILE)
        
        print("\n" + "=" * 60)
        print("BUILD COMPLETE!")
        print(f"Output: {OUTPUT_FILE}")
        print(f"Size: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")
        print("=" * 60)
        
    finally:
        cleanup(TEMP_DIR)


if __name__ == "__main__":
    main()
