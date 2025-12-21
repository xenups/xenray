import json
import os
from unittest.mock import mock_open, patch

import pytest

from src.core.i18n import I18n, get_available_languages, get_language, is_rtl, set_language


class TestI18n:
    @pytest.fixture(autouse=True)
    def reset_i18n(self):
        """Reset the I18n singleton and global instance before each test."""
        import src.core.i18n

        I18n._instance = None
        I18n._translations = {}
        I18n._current_lang = "en"
        # Re-create the global instance that functions use
        src.core.i18n._i18n = I18n()
        yield

    def test_singleton(self):
        """Test that I18n is a singleton."""
        i1 = I18n()
        i2 = I18n()
        assert i1 is i2

    def test_lazy_initialization(self):
        """Test that initialization is deferred."""
        i18n = I18n()
        # It's initially not initialized
        assert getattr(i18n, "_initialized", False) is False

        # Trigger initialization via public API
        with patch.object(I18n, "_load_translations"):
            lang = get_language()
            assert lang == "en"
            assert i18n._initialized is True

    def test_skip_i18n_env(self):
        """Test XENRAY_SKIP_I18N behavior."""
        with patch.dict(os.environ, {"XENRAY_SKIP_I18N": "1"}):
            # We need to re-initialize for this test because _ensure_initialized
            # checks the env var at that moment
            i18n = I18n()
            i18n._ensure_initialized()
            assert i18n._translations == {}
            assert i18n.t("any.key") == "any.key"

    def test_translation_loading(self):
        """Test loading translations from files."""
        mock_data = {"test": "Test English"}

        with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))), patch(
            "os.path.exists", return_value=True
        ):
            i18n = I18n()
            i18n._load_lang("en")
            assert i18n.t("test") == "Test English"

    def test_nested_translation(self):
        """Test accessing nested translation keys."""
        i18n = I18n()
        i18n._translations = {
            "en": {
                "settings": {
                    "general": "General Settings",
                    "advanced": "Advanced {name}",
                }
            }
        }
        i18n._initialized = True

        # Test via instance
        assert i18n.t("settings.general") == "General Settings"
        assert i18n.t("settings.advanced", name="Mode") == "Advanced Mode"
        assert i18n.t("non.existent") == "non.existent"

    def test_fallback_to_english(self):
        """Test fallback to English when key is missing in chosen language."""
        i18n = I18n()
        i18n._translations = {
            "en": {"only_en": "English Only"},
            "fa": {"both": "هر دو"},
        }
        i18n._initialized = True

        i18n.set_language("fa")
        assert i18n.t("both") == "هر دو"
        assert i18n.t("only_en") == "English Only"

    def test_rtl_check(self):
        """Test RTL detection."""
        set_language("en")
        assert is_rtl() is False

        set_language("fa")
        assert is_rtl() is True

    def test_available_languages(self):
        """Test get_available_languages."""
        langs = get_available_languages()
        assert "en" in langs
        assert "fa" in langs
        assert langs["fa"] == "فارسی"
