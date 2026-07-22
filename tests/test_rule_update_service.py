"""Tests for RuleUpdateService."""
import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.services.rule_update_service import RuleUpdateService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_rules_dir(tmp_path):
    """Temporarily redirect RULES_DIR to a temp path."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    with patch("src.services.rule_update_service.RULES_DIR", str(rules_dir)):
        yield str(rules_dir)


# ---------------------------------------------------------------------------
# get_rules_dir
# ---------------------------------------------------------------------------


class TestGetRulesDir:
    def test_creates_directory(self, mock_rules_dir):
        path = RuleUpdateService.get_rules_dir()
        assert os.path.exists(path)
        assert path == mock_rules_dir


# ---------------------------------------------------------------------------
# Version markers
# ---------------------------------------------------------------------------


class TestVersionMarkers:
    def test_get_local_unknown(self, mock_rules_dir):
        assert RuleUpdateService.get_local_rule_version("geoip") is None

    def test_save_and_read(self, mock_rules_dir):
        RuleUpdateService._save_version_marker("geoip", "2025.01.15")
        assert RuleUpdateService.get_local_rule_version("geoip") == "2025.01.15"

    def test_save_and_read_geosite(self, mock_rules_dir):
        RuleUpdateService._save_version_marker("geosite", "2025.02.01")
        assert RuleUpdateService.get_local_rule_version("geosite") == "2025.02.01"

    def test_overwrites_marker(self, mock_rules_dir):
        RuleUpdateService._save_version_marker("geoip", "old")
        RuleUpdateService._save_version_marker("geoip", "new")
        assert RuleUpdateService.get_local_rule_version("geoip") == "new"


# ---------------------------------------------------------------------------
# get_latest_rule_version
# ---------------------------------------------------------------------------


class TestGetLatestVersion:
    @patch("src.services.rule_update_service.requests.get")
    def test_returns_tag_name(self, mock_get):
        mock_get.return_value.json.return_value = {"tag_name": "v2025.01.15"}
        mock_get.return_value.raise_for_status = Mock()
        version = RuleUpdateService.get_latest_rule_version("geoip")
        assert version == "2025.01.15"

    @patch("src.services.rule_update_service.requests.get")
    def test_strips_v_prefix(self, mock_get):
        mock_get.return_value.json.return_value = {"tag_name": "v2025.01.15"}
        mock_get.return_value.raise_for_status = Mock()
        version = RuleUpdateService.get_latest_rule_version("geoip")
        assert version == "2025.01.15"

    @patch("src.services.rule_update_service.requests.get")
    def test_returns_none_on_failure(self, mock_get):
        mock_get.side_effect = Exception("API error")
        version = RuleUpdateService.get_latest_rule_version("geoip")
        assert version is None


# ---------------------------------------------------------------------------
# download_rule
# ---------------------------------------------------------------------------


class TestDownloadRule:
    @patch("src.services.rule_update_service.requests.get")
    def test_downloads_geoip(self, mock_get, mock_rules_dir):
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "4096"}
        mock_response.iter_content.return_value = [b"x" * 4096]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RuleUpdateService.download_rule("geoip")
        assert result is not None
        assert os.path.exists(result)
        assert result.endswith("geoip.dat")
        assert os.path.getsize(result) == 4096

    @patch("src.services.rule_update_service.requests.get")
    def test_downloads_geosite(self, mock_get, mock_rules_dir):
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "8192"}
        mock_response.iter_content.return_value = [b"y" * 8192]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RuleUpdateService.download_rule("geosite")
        assert result is not None
        assert os.path.exists(result)
        assert result.endswith("geosite.dat")
        assert os.path.getsize(result) == 8192

    @patch("src.services.rule_update_service.requests.get")
    def test_retries_and_fails(self, mock_get, mock_rules_dir):
        mock_get.side_effect = Exception("Network error")
        result = RuleUpdateService.download_rule("geoip")
        assert result is None
        assert mock_get.call_count == 3  # MAX_RETRIES

    @patch("src.services.rule_update_service.requests.get")
    def test_rejects_small_file(self, mock_get, mock_rules_dir):
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "100"}
        mock_response.iter_content.return_value = [b"s" * 100]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RuleUpdateService.download_rule("geoip")
        assert result is None

    @patch("src.services.rule_update_service.requests.get")
    def test_calls_progress(self, mock_get, mock_rules_dir):
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "4096"}
        mock_response.iter_content.return_value = [b"x" * 4096]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        messages = []
        RuleUpdateService.download_rule("geoip", progress_callback=messages.append)
        assert any("geoip.dat" in m for m in messages)


# ---------------------------------------------------------------------------
# update_rules
# ---------------------------------------------------------------------------


class TestUpdateRules:
    @patch("src.services.rule_update_service.RuleUpdateService.download_rule")
    def test_both_files_downloaded(self, mock_download, mock_rules_dir):
        mock_download.return_value = "/fake/path/geoip.dat"
        result = RuleUpdateService.update_rules()
        assert result is True
        assert mock_download.call_count == 2

    @patch("src.services.rule_update_service.RuleUpdateService.download_rule")
    def test_returns_false_if_one_fails(self, mock_download, mock_rules_dir):
        mock_download.side_effect = ["/fake/path/geoip.dat", None]
        result = RuleUpdateService.update_rules()
        assert result is False
        assert mock_download.call_count == 2

    @patch("src.services.rule_update_service.RuleUpdateService.download_rule")
    def test_passes_progress_callback(self, mock_download, mock_rules_dir):
        callback = Mock()
        RuleUpdateService.update_rules(progress_callback=callback)
        assert mock_download.call_count == 2


# ---------------------------------------------------------------------------
# check_for_updates
# ---------------------------------------------------------------------------


class TestCheckForUpdates:
    @patch("src.services.rule_update_service.RuleUpdateService.get_latest_rule_version")
    @patch("src.services.rule_update_service.RuleUpdateService.get_local_rule_version")
    def test_update_available(self, mock_local, mock_latest, mock_rules_dir):
        mock_latest.return_value = "2025.02.01"
        mock_local.return_value = "2025.01.01"
        available, local, latest = RuleUpdateService.check_for_updates()
        assert available is True
        assert local == "2025.01.01"
        assert latest == "2025.02.01"

    @patch("src.services.rule_update_service.RuleUpdateService.get_latest_rule_version")
    @patch("src.services.rule_update_service.RuleUpdateService.get_local_rule_version")
    def test_up_to_date(self, mock_local, mock_latest, mock_rules_dir):
        mock_latest.return_value = "2025.02.01"
        mock_local.return_value = "2025.02.01"
        available, local, latest = RuleUpdateService.check_for_updates()
        assert available is False
        assert local == "2025.02.01"
        assert latest == "2025.02.01"

    @patch("src.services.rule_update_service.RuleUpdateService.get_latest_rule_version")
    def test_no_local_version(self, mock_latest, mock_rules_dir):
        mock_latest.return_value = "2025.02.01"
        available, local, latest = RuleUpdateService.check_for_updates()
        assert available is True  # local is None, so update is available
        assert local is None

    @patch("src.services.rule_update_service.RuleUpdateService.get_latest_rule_version")
    def test_no_latest(self, mock_latest, mock_rules_dir):
        mock_latest.return_value = None
        available, local, latest = RuleUpdateService.check_for_updates()
        assert available is False
        assert latest is None
