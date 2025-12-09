"""
City name translation using offline compressed database.

This module provides O(1) lookups for city names in multiple languages
using a pre-built MessagePack + Zstandard compressed database.

The database is loaded once at startup and kept in memory for fast access.
"""

import os
from pathlib import Path
from typing import Optional

# Lazy imports to avoid startup delay if not used
_db: Optional[dict] = None
_db_loaded = False


def _get_data_path() -> Path:
    """Get path to the city database file."""
    # Try relative to this file first
    module_dir = Path(__file__).parent
    data_path = module_dir.parent.parent / "assets" / "data" / "cities.msgpack.zst"
    
    if data_path.exists():
        return data_path
    
    # Try relative to exe for PyInstaller builds
    import sys
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        data_path = exe_dir / "assets" / "data" / "cities.msgpack.zst"
        if data_path.exists():
            return data_path
    
    return data_path


def _load_database() -> dict:
    """Load and decompress the city database."""
    global _db, _db_loaded
    
    if _db_loaded:
        return _db or {}
    
    data_path = _get_data_path()
    
    if not data_path.exists():
        # Database not built yet - return empty dict
        _db = {}
        _db_loaded = True
        return _db
    
    try:
        import msgpack
        import zstandard as zstd
        
        # Read compressed data
        with open(data_path, "rb") as f:
            compressed = f.read()
        
        # Decompress
        decompressor = zstd.ZstdDecompressor()
        packed = decompressor.decompress(compressed)
        
        # Deserialize
        _db = msgpack.unpackb(packed, raw=False)
        _db_loaded = True
        
        return _db
        
    except Exception as e:
        print(f"[city_translator] Failed to load database: {e}")
        _db = {}
        _db_loaded = True
        return _db


def translate_city(city_name: str, lang: str = None, fallback: str = None) -> str:
    """
    Translate a city name to the specified language.
    
    Args:
        city_name: City name in any language (will be normalized)
        lang: Target language code (en, fa, ru, zh). If None, uses current app language.
        fallback: Fallback value if translation not found
    
    Returns:
        Translated city name or fallback/original
    """
    if not city_name:
        return fallback or ""
    
    # Get current language if not specified
    if lang is None:
        try:
            from src.core.i18n import get_language
            lang = get_language()
        except ImportError:
            lang = "en"
    
    # Load database
    db = _load_database()
    
    if not db:
        return fallback or city_name
    
    # Normalize key
    key = city_name.lower().strip()
    
    # Lookup
    entry = db.get(key)
    
    if entry:
        # Return translated name or fallback to English
        return entry.get(lang) or entry.get("en") or fallback or city_name
    
    # Not found - return original
    return fallback or city_name


def get_city_translations(city_name: str) -> Optional[dict]:
    """
    Get all translations for a city.
    
    Returns:
        Dict with {en, fa, ru, zh} translations or None if not found
    """
    if not city_name:
        return None
    
    db = _load_database()
    key = city_name.lower().strip()
    return db.get(key)


def is_database_loaded() -> bool:
    """Check if the city database is available."""
    db = _load_database()
    return bool(db)


def get_database_stats() -> dict:
    """Get statistics about the loaded database."""
    db = _load_database()
    return {
        "loaded": bool(db),
        "entries": len(db) if db else 0,
        "path": str(_get_data_path()),
    }
