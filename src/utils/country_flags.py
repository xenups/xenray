"""Country flag utilities for server locations."""
import re

# Emoji flags for countries (Unicode)
COUNTRY_FLAGS = {
    "us": "🇺🇸", "usa": "🇺🇸", "united states": "🇺🇸", "america": "🇺🇸",
    "uk": "🇬🇧", "gb": "🇬🇧", "united kingdom": "🇬🇧", "england": "🇬🇧",
    "de": "🇩🇪", "germany": "🇩🇪",
    "fr": "🇫🇷", "france": "🇫🇷",
    "nl": "🇳🇱", "netherlands": "🇳🇱",
    "ca": "🇨🇦", "canada": "🇨🇦",
    "jp": "🇯🇵", "japan": "🇯🇵",
    "sg": "🇸🇬", "singapore": "🇸🇬",
    "au": "🇦🇺", "australia": "🇦🇺",
    "hk": "🇭🇰", "hong kong": "🇭🇰", "hongkong": "🇭🇰",
    "tw": "🇹🇼", "taiwan": "🇹🇼",
    "kr": "🇰🇷", "korea": "🇰🇷", "south korea": "🇰🇷",
    "in": "🇮🇳", "india": "🇮🇳",
    "ru": "🇷🇺", "russia": "🇷🇺",
    "br": "🇧🇷", "brazil": "🇧🇷",
    "se": "🇸🇪", "sweden": "🇸🇪",
    "ch": "🇨🇭", "switzerland": "🇨🇭",
    "es": "🇪🇸", "spain": "🇪🇸",
    "it": "🇮🇹", "italy": "🇮🇹",
    "pl": "🇵🇱", "poland": "🇵🇱",
    "tr": "🇹🇷", "turkey": "🇹🇷",
    "ae": "🇦🇪", "uae": "🇦🇪", "dubai": "🇦🇪",
    "ir": "🇮🇷", "iran": "🇮🇷",
    "cn": "🇨🇳", "china": "🇨🇳",
    "fi": "🇫🇮", "fl": "🇫🇮", "finland": "🇫🇮",
    "hu": "🇭🇺", "hungary": "🇭🇺",
    "at": "🇦🇹", "austria": "🇦🇹",
    "be": "🇧🇪", "belgium": "🇧🇪",
    "cz": "🇨🇿", "czech": "🇨🇿", "czechia": "🇨🇿",
    "dk": "🇩🇰", "denmark": "🇩🇰",
    "no": "🇳🇴", "norway": "🇳🇴",
    "pt": "🇵🇹", "portugal": "🇵🇹",
    "ro": "🇷🇴", "romania": "🇷🇴",
}

def get_country_flag(name: str) -> str:
    """
    Extract country flag from server name.
    
    Args:
        name: Server name (e.g., "US Server 1", "Germany-Fast", "🇯🇵 Tokyo", "FL-HU")
        
    Returns:
        Country flag emoji or empty string
    """
    print(f"[CountryFlags] get_country_flag called with: '{name}'")
    
    if not name:
        return ""
    
    # Check if name already contains a flag emoji
    flag_pattern = re.compile(r'[\U0001F1E6-\U0001F1FF]{2}')
    match = flag_pattern.search(name)
    if match:
        print(f"[CountryFlags] Found existing flag emoji: {match.group(0)}")
        return match.group(0)
    
    # Remove all emojis and special characters, keep only letters, numbers, spaces, and dashes
    # This handles cases like "☁️FL-VLESS HU"
    cleaned_name = re.sub(r'[^\w\s-]', '', name, flags=re.UNICODE)
    cleaned_name = re.sub(r'[\U0001F000-\U0001FFFF]', '', cleaned_name)  # Remove emojis
    name_lower = cleaned_name.lower().strip()
    
    print(f"[CountryFlags] Cleaned name: '{cleaned_name}' -> lowercase: '{name_lower}'")
    
    # Try to match 2-letter codes (most common case)
    # Look for patterns like "FL-", "FL ", "FL" at start, "-FL-", "-FL ", etc.
    for key, flag in COUNTRY_FLAGS.items():
        if len(key) == 2:
            # Check if the 2-letter code appears in the name
            # Match at start, after dash/space, or before dash/space
            if name_lower.startswith(key + '-') or \
               name_lower.startswith(key + ' ') or \
               (name_lower.startswith(key) and len(name_lower) == 2):
                print(f"[CountryFlags] Matched '{key}' at start -> flag value: '{flag}' (repr: {repr(flag)})")
                # Verify we're returning the emoji, not the key
                if len(flag) >= 2 and ord(flag[0]) >= 0x1F1E6:
                    return flag
                else:
                    print(f"[CountryFlags] WARNING: Flag value seems wrong, returning default")
                    return "🌐"
    
    # Try matching after dash or space (but not at end to avoid matching last code)
    for key, flag in COUNTRY_FLAGS.items():
        if len(key) == 2:
            if ('-' + key + '-') in name_lower or \
               ('-' + key + ' ') in name_lower or \
               (' ' + key + '-') in name_lower or \
               (' ' + key + ' ') in name_lower:
                print(f"[CountryFlags] Matched '{key}' in middle -> flag value: '{flag}'")
                return flag
    
    # Try longer country names (full names)
    for key, flag in COUNTRY_FLAGS.items():
        if len(key) > 2 and key in name_lower:
            print(f"[CountryFlags] Matched '{key}' -> flag value: '{flag}'")
            return flag
    
    print(f"[CountryFlags] No match for '{name}', using default")
    return "🌐"  # Default globe icon

def get_country_from_ip(ip: str) -> str:
    """
    Get country flag from IP address using ip-api.com.
    
    Args:
        ip: IP address to lookup
        
    Returns:
        Country flag emoji or globe icon
    """
    try:
        import requests
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=3)
        if response.status_code == 200:
            data = response.json()
            country_code = data.get('countryCode', '')
            
            if country_code and len(country_code) == 2:
                # Convert country code to flag emoji
                # Country codes are 2 letters (uppercase), flags are regional indicator symbols
                country_code = country_code.upper()
                # Regional Indicator Symbol Letter A is U+1F1E6
                # For 'CA': C=0x1F1E8, A=0x1F1E6
                flag = chr(0x1F1E6 + ord(country_code[0]) - ord('A')) + \
                       chr(0x1F1E6 + ord(country_code[1]) - ord('A'))
                print(f"[CountryFlags] IP {ip} -> {country_code} {flag}")
                return flag
            else:
                print(f"[CountryFlags] Invalid country code for IP {ip}: {country_code}")
    except Exception as e:
        print(f"[CountryFlags] Failed to get country for IP {ip}: {e}")
    
    return "🌐"  # Default globe icon
