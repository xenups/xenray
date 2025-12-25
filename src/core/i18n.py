"""Internationalization (i18n) manager for multilingual support."""
from __future__ import annotations

import json
import os
from typing import Optional

from src.core.logger import logger


class I18n:
    """Simple internationalization manager for Persian/English support."""

    _instance: Optional["I18n"] = None
    _translations: dict = {}
    _current_lang: str = "en"
    _available_languages = {
        "en": "English",
        "fa": "فارسی",
        "zh": "中文",
        "ru": "Русский",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Initialization is deferred to avoid early side effects (logs)
            cls._instance._initialized = False
        return cls._instance

    def _ensure_initialized(self):
        """Ensure translations are loaded before use."""
        if getattr(self, "_initialized", False):
            return

        import os

        if os.getenv("XENRAY_SKIP_I18N"):
            # In CLI mode, we don't load anything to keep it clean and fast
            self._translations = {}
        else:
            self._load_translations()

        self._initialized = True

    def _load_lang(self, lang: str):
        """Load specific language translation."""
        locales_dir = self._get_locales_dir()
        path = os.path.join(locales_dir, f"{lang}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._translations[lang] = json.load(f)
                logger.debug(f"Loaded {lang} translations")
        except Exception as e:
            logger.error(f"Error loading {lang} translations: {e}")

    def _get_locales_dir(self) -> str:
        """Get the locales directory path."""
        import sys

        if getattr(sys, "frozen", False):
            root = os.path.dirname(sys.executable)
        else:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root, "assets", "locales")

    def _load_translations(self):
        """Load all translation files."""
        for lang in self._available_languages.keys():
            self._load_lang(lang)

    def set_language(self, lang: str):
        """Set the current language."""
        if lang in self._available_languages:
            self._current_lang = lang
            logger.debug(f"Language set to: {lang}")
        else:
            logger.warning(f"Unknown language: {lang}")

    @property
    def current_language(self) -> str:
        return self._current_lang

    @property
    def is_rtl(self) -> bool:
        """Check if current language is RTL (right-to-left)."""
        return self._current_lang == "fa"

    @property
    def available_languages(self) -> dict:
        return self._available_languages

    def t(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """
        Translate a key to the current language.

        Args:
            key: Dot-separated key path (e.g., "settings.general")
            default: Default value if key not found (useful for CLI/English fallback)
            **kwargs: Format arguments for the string

        Returns:
            Translated string, default value, or the key itself as fallback
        """
        translations = self._translations.get(self._current_lang, {})

        # Navigate through nested keys
        keys = key.split(".")
        value = translations
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break

        if value is None:
            # Fallback to English
            value = self._translations.get("en", {})
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    value = None
                    break

        if value is None:
            return default if default is not None else key  # Return default or key as fallback

        # Support string formatting
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value

        return value


# Global instance (initially uninitialized)
_i18n = I18n()


def _get_i18n():
    """Get the initialized i18n instance."""
    _i18n._ensure_initialized()
    return _i18n


def t(key: str, default: Optional[str] = None, **kwargs) -> str:
    """Shortcut function for translation with optional default."""
    return _get_i18n().t(key, default=default, **kwargs)


def set_language(lang: str):
    """Set the application language."""
    _get_i18n().set_language(lang)


def get_language() -> str:
    """Get current language code."""
    return _get_i18n().current_language


def is_rtl() -> bool:
    """Check if current language is RTL."""
    return _get_i18n().is_rtl


def get_available_languages() -> dict:
    """Get available languages."""
    return _get_i18n().available_languages
