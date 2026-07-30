"""Country flag utilities for server locations."""
import re
from typing import Optional

from loguru import logger

# Emoji flags for countries (Unicode)
COUNTRY_FLAGS = {
    "us": "🇺🇸",
    "usa": "🇺🇸",
    "united states": "🇺🇸",
    "america": "🇺🇸",
    "uk": "🇬🇧",
    "gb": "🇬🇧",
    "united kingdom": "🇬🇧",
    "england": "🇬🇧",
    "de": "🇩🇪",
    "germany": "🇩🇪",
    "fr": "🇫🇷",
    "france": "🇫🇷",
    "nl": "🇳🇱",
    "netherlands": "🇳🇱",
    "ca": "🇨🇦",
    "canada": "🇨🇦",
    "jp": "🇯🇵",
    "japan": "🇯🇵",
    "sg": "🇸🇬",
    "singapore": "🇸🇬",
    "au": "🇦🇺",
    "australia": "🇦🇺",
    "hk": "🇭🇰",
    "hong kong": "🇭🇰",
    "hongkong": "🇭🇰",
    "tw": "🇹🇼",
    "taiwan": "🇹🇼",
    "kr": "🇰🇷",
    "korea": "🇰🇷",
    "south korea": "🇰🇷",
    "in": "🇮🇳",
    "india": "🇮🇳",
    "ru": "🇷🇺",
    "russia": "🇷🇺",
    "br": "🇧🇷",
    "brazil": "🇧🇷",
    "se": "🇸🇪",
    "sweden": "🇸🇪",
    "ch": "🇨🇭",
    "switzerland": "🇨🇭",
    "es": "🇪🇸",
    "spain": "🇪🇸",
    "it": "🇮🇹",
    "italy": "🇮🇹",
    "pl": "🇵🇱",
    "poland": "🇵🇱",
    "tr": "🇹🇷",
    "turkey": "🇹🇷",
    "ae": "🇦🇪",
    "uae": "🇦🇪",
    "dubai": "🇦🇪",
    "ir": "🇮🇷",
    "iran": "🇮🇷",
    "cn": "🇨🇳",
    "china": "🇨🇳",
    "fi": "🇫🇮",
    "fl": "🇫🇮",
    "finland": "🇫🇮",
    "hu": "🇭🇺",
    "hungary": "🇭🇺",
    "at": "🇦🇹",
    "austria": "🇦🇹",
    "be": "🇧🇪",
    "belgium": "🇧🇪",
    "cz": "🇨🇿",
    "czech": "🇨🇿",
    "czechia": "🇨🇿",
    "dk": "🇩🇰",
    "denmark": "🇩🇰",
    "no": "🇳🇴",
    "norway": "🇳🇴",
    "pt": "🇵🇹",
    "portugal": "🇵🇹",
    "ro": "🇷🇴",
    "romania": "🇷🇴",
}

# Constants
DEFAULT_FLAG = "🌐"
FLAG_EMOJI_PATTERN = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
IP_API_TIMEOUT = 3.0  # seconds
REGIONAL_INDICATOR_BASE = 0x1F1E6  # Regional Indicator Symbol Letter A


def get_country_flag(name: str) -> str:
    """
    Extract country flag from server name.

    Args:
        name: Server name (e.g., "US Server 1", "Germany-Fast", "🇯🇵 Tokyo", "FL-HU")

    Returns:
        Country flag emoji or default globe icon
    """
    if not name or not isinstance(name, str):
        return DEFAULT_FLAG

    # Check if name already contains a flag emoji
    match = FLAG_EMOJI_PATTERN.search(name)
    if match:
        logger.trace(f"Found existing flag emoji: {match.group(0)}")
        return match.group(0)

    # Remove all emojis and special characters, keep only letters, numbers, spaces, and dashes
    # This handles cases like "☁️FL-VLESS HU"
    cleaned_name = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    cleaned_name = re.sub(r"[\U0001F000-\U0001FFFF]", "", cleaned_name)  # Remove emojis
    name_lower = cleaned_name.lower().strip()

    logger.trace(f"Cleaned name: '{cleaned_name}' -> lowercase: '{name_lower}'")

    # Try to match 2-letter codes (most common case)
    # Look for patterns like "FL-", "FL ", "FL" at start, "-FL-", "-FL ", etc.
    for key, flag in COUNTRY_FLAGS.items():
        if len(key) == 2:
            # Check if the 2-letter code appears in the name
            # Match at start, after dash/space, or before dash/space
            if (
                name_lower.startswith(key + "-")
                or name_lower.startswith(key + " ")
                or (name_lower.startswith(key) and len(name_lower) == 2)
            ):
                logger.trace(f"Matched '{key}' at start -> flag: '{flag}'")
                # Verify we're returning the emoji, not the key
                if len(flag) >= 2 and ord(flag[0]) >= REGIONAL_INDICATOR_BASE:
                    return flag
                else:
                    logger.warning(f"Flag value seems wrong for '{key}', using default")
                    return DEFAULT_FLAG

    # Try matching after dash or space (but not at end to avoid matching last code)
    for key, flag in COUNTRY_FLAGS.items():
        if len(key) == 2:
            if (
                ("-" + key + "-") in name_lower
                or ("-" + key + " ") in name_lower
                or (" " + key + "-") in name_lower
                or (" " + key + " ") in name_lower
            ):
                logger.trace(f"Matched '{key}' in middle -> flag: '{flag}'")
                return flag

    # Try longer country names (full names)
    for key, flag in COUNTRY_FLAGS.items():
        if len(key) > 2 and key in name_lower:
            logger.trace(f"Matched '{key}' -> flag: '{flag}'")
            return flag

    logger.debug(f"No match for '{name}', using default")
    return DEFAULT_FLAG


def country_code_to_flag(country_code: str) -> str:
    """
    Convert a 2-letter country code to an emoji flag.

    Args:
        country_code: 2-letter uppercase country code (e.g., "US", "IR")

    Returns:
        Country flag emoji or default globe icon
    """
    if not country_code or len(country_code) != 2:
        return DEFAULT_FLAG

    country_code = country_code.upper()
    try:
        # Regional Indicator Symbol Letter A is U+1F1E6
        # For 'CA': C=0x1F1E8, A=0x1F1E6
        return chr(REGIONAL_INDICATOR_BASE + ord(country_code[0]) - ord("A")) + chr(
            REGIONAL_INDICATOR_BASE + ord(country_code[1]) - ord("A")
        )
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to convert country code {country_code} to flag: {e}")
        return DEFAULT_FLAG


from src.services.ip_geolocation_service import fetch_country_info_from_ip, fetch_public_exit_ip


def get_country_from_ip(ip: str) -> str:
    """
    Get country flag from IP address using IPGeolocationService.

    Args:
        ip: IP address to lookup

    Returns:
        Country flag emoji or default globe icon
    """
    code, _ = fetch_country_info_from_ip(ip)
    if code:
        return country_code_to_flag(code)
    return DEFAULT_FLAG
