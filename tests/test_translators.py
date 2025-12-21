from unittest.mock import MagicMock, patch

from src.core.city_translator import _load_database, translate_city
from src.core.country_translator import translate_country


class TestTranslators:
    @patch("pycountry.countries.get")
    @patch("src.core.country_translator.get_language")
    @patch("src.core.country_translator._get_translator")
    def test_translate_country_en(self, mock_get_trans, mock_get_lang, mock_countries_get):
        """Test country translation to English."""
        mock_get_lang.return_value = "en"
        country_mock = MagicMock()
        country_mock.name = "Germany"
        mock_countries_get.return_value = country_mock

        assert translate_country("DE") == "Germany"

    @patch("pycountry.countries.get")
    @patch("src.core.country_translator.get_language")
    @patch("src.core.country_translator._get_translator")
    def test_translate_country_fa(self, mock_get_trans, mock_get_lang, mock_countries_get):
        """Test country translation to Persian."""
        mock_get_lang.return_value = "fa"
        country_mock = MagicMock()
        country_mock.name = "Germany"
        mock_countries_get.return_value = country_mock

        translator_mock = MagicMock()
        translator_mock.gettext.return_value = "آلمان"
        mock_get_trans.return_value = translator_mock

        assert translate_country("DE") == "آلمان"

    def test_translate_country_not_found(self):
        """Test country translation fallback when country code is unknown."""
        with patch("pycountry.countries.get", return_value=None):
            assert translate_country("XX") == "XX"
            assert translate_country("XX", fallback="Unknown") == "Unknown"

    @patch("src.core.city_translator._load_database")
    def test_translate_city_success(self, mock_load_db):
        """Test city translation from mocked database."""
        mock_load_db.return_value = {"berlin": {"en": "Berlin", "fa": "برلین"}}

        # Pass lang directly to avoid mocking local import in translate_city
        assert translate_city("Berlin", lang="fa") == "برلین"
        assert translate_city("berlin", lang="fa") == "برلین"

    @patch("src.core.city_translator._load_database")
    def test_translate_city_fallback(self, mock_load_db):
        """Test city translation fallback to original name."""
        mock_load_db.return_value = {}
        assert translate_city("UnknownCity") == "UnknownCity"
        assert translate_city("UnknownCity", fallback="Default") == "Default"

    @patch("src.core.city_translator._get_data_path")
    def test_load_database_not_exists(self, mock_get_path):
        """Test loading database when file does not exist."""
        mock_get_path.return_value = MagicMock(exists=lambda: False)
        # Reset global state for testing load_database
        import src.core.city_translator

        src.core.city_translator._db_loaded = False
        src.core.city_translator._db = None

        db = _load_database()
        assert db == {}
