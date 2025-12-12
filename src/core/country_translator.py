"""Country name translations using pycountry library."""
import gettext

import pycountry

from src.core.i18n import get_language

# Mapping of app language codes to pycountry locale codes
LANG_TO_LOCALE = {
    "en": "en",
    "fa": "fa",  # Persian/Farsi
    "zh": "zh_CN",  # Simplified Chinese
    "ru": "ru",
}

# Cache for gettext translators
_translators: dict = {}


def _get_translator(lang_code: str):
    """Get or create a gettext translator for the given language."""
    if lang_code not in _translators:
        try:
            locale = LANG_TO_LOCALE.get(lang_code, lang_code)
            translator = gettext.translation(
                "iso3166-1",
                pycountry.LOCALES_DIR,
                languages=[locale],
            )
            _translators[lang_code] = translator
        except (FileNotFoundError, OSError):
            # Fallback to null translation if locale not found
            _translators[lang_code] = None
    return _translators.get(lang_code)


def translate_country(country_code: str, fallback: str = None) -> str:
    """
    Translate a country code to the current language using pycountry.

    Args:
        country_code: ISO 2-letter country code (e.g., 'US', 'DE')
        fallback: Fallback name if translation not found

    Returns:
        Translated country name or fallback/code
    """
    if not country_code:
        return fallback or "Unknown"

    code = country_code.upper()

    try:
        # Get country from pycountry
        country = pycountry.countries.get(alpha_2=code)
        if not country:
            return fallback or code

        english_name = country.name

        # Get current language
        lang = get_language()

        # If English, return directly
        if lang == "en":
            return english_name

        # Try to get translation
        translator = _get_translator(lang)
        if translator:
            translated = translator.gettext(english_name)
            if translated and translated != english_name:
                return translated

        # Fallback to English name
        return english_name

    except Exception:
        return fallback or code


def translate_city(city_name: str) -> str:
    """
    Cities are usually kept in their original form.
    This could be extended with city translation libraries if needed.
    """
    return city_name or ""
