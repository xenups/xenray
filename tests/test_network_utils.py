"""Tests for NetworkUtils — connectivity checks (F8 fail-closed, F9 per-socket timeout)."""

from __future__ import annotations

from unittest.mock import patch

from src.utils.network_utils import NetworkUtils


class TestCheckProxyConnectivity:
    """F8: curl missing must fail CLOSED (probe failed), never succeed."""

    def test_curl_missing_returns_false(self):
        with patch("src.utils.network_utils.shutil.which", return_value=None):
            assert NetworkUtils.check_proxy_connectivity(port=10805) is False

    def test_curl_present_uses_curl(self):
        with patch("src.utils.network_utils.shutil.which", return_value="C:/curl/curl.exe"):
            with patch("src.utils.network_utils.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "204"
                assert NetworkUtils.check_proxy_connectivity(port=10805) is True

    def test_curl_present_but_http_error_returns_false(self):
        with patch("src.utils.network_utils.shutil.which", return_value="curl"):
            with patch("src.utils.network_utils.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "000"
                assert NetworkUtils.check_proxy_connectivity(port=10805) is False


class TestCheckInternetConnection:
    """F9: timeout must be set per-socket, never via process-global default."""

    def test_success_uses_per_socket_settimeout(self):
        calls = {"settimeout": None, "connect": None}

        class FakeSocket:
            def __init__(self, *args, **kwargs):
                self._closed = False

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self._closed = True
                return False

            def settimeout(self, timeout):
                calls["settimeout"] = timeout

            def connect(self, addr):
                calls["connect"] = addr

        with patch("src.utils.network_utils.socket.socket", FakeSocket):
            with patch("src.utils.network_utils.socket.setdefaulttimeout") as mock_default:
                assert NetworkUtils.check_internet_connection(host="8.8.8.8", port=53, timeout=3, retries=1) is True
                mock_default.assert_not_called()

        assert calls["settimeout"] == 3
        assert calls["connect"] == ("8.8.8.8", 53)

    def test_failure_returns_false(self):
        with patch("src.utils.network_utils.socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.connect.side_effect = OSError("timeout")
            assert NetworkUtils.check_internet_connection(retries=1) is False

    def test_never_sets_process_global_default(self):
        """The process-global socket default timeout must NEVER be touched."""
        with patch("src.utils.network_utils.socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.connect.side_effect = OSError("timeout")
            with patch("src.utils.network_utils.socket.setdefaulttimeout") as mock_default:
                NetworkUtils.check_internet_connection(host="8.8.8.8", port=53, timeout=3, retries=2)
                mock_default.assert_not_called()
