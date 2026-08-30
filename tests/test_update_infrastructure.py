"""Tests for the fortified update infrastructure (file-lock-safe core extraction
and the interactive UpdateDialog)."""

from __future__ import annotations

import hashlib
import os
import zipfile
from unittest.mock import Mock, patch

from src.services.installer.archive_extractor import OLD_SUFFIX, ArchiveExtractor


def _make_zip(zip_path, contents):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in contents.items():
            zf.writestr(name, data)


def test_extract_core_safe_rename_replaces_binary(tmp_path, monkeypatch):
    """Existing xray.exe must be safely renamed away, replaced, and the .old
    backup cleaned up on success (no PermissionError on locked files)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self: None)

    old = bin_dir / "xray.exe"
    old.write_bytes(b"OLD_BINARY")

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    assert ArchiveExtractor(str(bin_dir)).extract_core(str(zip_path)) is True
    assert (bin_dir / "xray.exe").read_bytes() == b"NEW_BINARY"
    assert not (bin_dir / ("xray.exe" + OLD_SUFFIX)).exists(), ".old backup must be cleaned up"


def test_extract_core_rolls_back_on_failure(tmp_path, monkeypatch):
    """If extraction fails, the previous binary must be restored (rollback)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self: None)

    old = bin_dir / "xray.exe"
    old.write_bytes(b"OLD_BINARY")

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    real_extractall = zipfile.ZipFile.extractall

    def _failing_extractall(self, *a, **k):
        raise OSError("Permission denied")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", _failing_extractall)
    try:
        assert ArchiveExtractor(str(bin_dir)).extract_core(str(zip_path)) is False
    finally:
        monkeypatch.setattr(zipfile.ZipFile, "extractall", real_extractall)

    assert (bin_dir / "xray.exe").read_bytes() == b"OLD_BINARY", "old binary restored"
    assert not (bin_dir / ("xray.exe" + OLD_SUFFIX)).exists(), ".old backup consumed by rollback"


def test_extract_core_calls_kill_before_replacing(tmp_path, monkeypatch):
    """Active xray processes must be killed before the binary is replaced."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    killed = []

    def _fake_kill(self):
        killed.append(True)

    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", _fake_kill)

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    ArchiveExtractor(str(bin_dir)).extract_core(str(zip_path))
    assert killed, "_kill_active_core must be called before extraction"


def test_extract_core_missing_zip_returns_false(tmp_path):
    """A missing zip must yield False, not raise."""
    assert ArchiveExtractor(str(tmp_path / "bin")).extract_core(str(tmp_path / "nope.zip")) is False

# ── SHA-256 verification tests ──────────────────────────────────────────────


class TestSha256Verification:
    """FileDownloader SHA-256 verification via .dgst sidecar."""

    def test_valid_sha256_accepted(self, tmp_path):
        """Download matching .dgst → file accepted."""
        from src.services.installer.file_downloader import FileDownloader

        payload = b"Xray-core binary payload content"
        zip_path = str(tmp_path / "test.zip")
        with open(zip_path, "wb") as f:
            f.write(payload)

        sha = hashlib.sha256(payload).hexdigest()

        fd = FileDownloader.__new__(FileDownloader)
        with patch.object(FileDownloader, "_fetch_expected_sha256", return_value=sha):
            assert fd._verify_sha256(zip_path, "https://example.com/test.zip")

    def test_mismatched_sha256_rejected(self, tmp_path):
        """Wrong hash → file deleted, returns False."""
        from src.services.installer.file_downloader import FileDownloader

        payload = b"tampered content"
        zip_path = str(tmp_path / "bad.zip")
        with open(zip_path, "wb") as f:
            f.write(payload)

        fd = FileDownloader.__new__(FileDownloader)
        with patch.object(FileDownloader, "_fetch_expected_sha256", return_value="0" * 64):
            assert not fd._verify_sha256(zip_path, "https://example.com/bad.zip")
        assert not os.path.exists(zip_path)

    def test_missing_dgst_skips_check(self, tmp_path):
        """404 on .dgst → verification skipped, file kept."""
        from src.services.installer.file_downloader import FileDownloader

        zip_path = str(tmp_path / "nodgst.zip")
        with open(zip_path, "wb") as f:
            f.write(b"data")

        fd = FileDownloader.__new__(FileDownloader)
        with patch.object(FileDownloader, "_fetch_expected_sha256", return_value=None):
            assert fd._verify_sha256(zip_path, "https://example.com/nodgst.zip")
        assert os.path.exists(zip_path)

    def test_sha256_hex_reads_file(self, tmp_path):
        """_sha256_hex returns correct hex digest."""
        from src.services.installer.file_downloader import FileDownloader

        path = str(tmp_path / "data.bin")
        content = b"hello xenray"
        with open(path, "wb") as f:
            f.write(content)

        expected = hashlib.sha256(content).hexdigest()
        assert FileDownloader._sha256_hex(path) == expected

    def test_sha256_hex_missing_file(self):
        """_sha256_hex returns None for nonexistent file."""
        from src.services.installer.file_downloader import FileDownloader

        assert FileDownloader._sha256_hex("/nonexistent/path") is None

    def test_fetch_dgst_parses_correctly(self):
        """_fetch_expected_sha256 extracts SHA2-256 line."""
        from src.services.installer.file_downloader import FileDownloader

        dgst_text = (
            "MD5= 402f65a8cccdf123a6c0d5c176ef5252\n"
            "SHA1= 42e5e9a66b970b5499c34e99d8da6c986c67c2cc\n"
            "SHA2-256= d004c39288ce9ada487c6f398c7c545f\n"
            "SHA2-512= 5b1356f07a91cbd4fb538fd7eccc4949\n"
        )
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, text=dgst_text, raise_for_status=Mock())
            result = FileDownloader._fetch_expected_sha256("https://example.com/test.dgst")
        assert result == "d004c39288ce9ada487c6f398c7c545f"

    def test_fetch_dgst_404_returns_none(self):
        """404 → None (no sidecar available)."""
        from src.services.installer.file_downloader import FileDownloader

        resp = Mock(status_code=404)
        with patch("requests.get", return_value=resp):
            assert FileDownloader._fetch_expected_sha256("https://example.com/missing.dgst") is None


class TestAppUpdateSha256:
    """AppUpdateService SHA-256 verification."""

    def test_valid_sha_accepted(self, tmp_path):
        from src.services.installer.app_update_service import AppUpdateService

        payload = b"app update zip"
        zip_path = str(tmp_path / "update.zip")
        with open(zip_path, "wb") as f:
            f.write(payload)

        sha = hashlib.sha256(payload).hexdigest()
        resp = Mock(status_code=200, text=f"SHA2-256= {sha}", raise_for_status=Mock())
        with patch("requests.get", return_value=resp):
            assert AppUpdateService._verify_app_sha256(zip_path, "https://example.com/update.zip")

    def test_mismatch_rejected(self, tmp_path):
        from src.services.installer.app_update_service import AppUpdateService

        zip_path = str(tmp_path / "bad.zip")
        with open(zip_path, "wb") as f:
            f.write(b"bad data")

        resp = Mock(status_code=200, text="SHA2-256= 0000", raise_for_status=Mock())
        with patch("requests.get", return_value=resp):
            assert not AppUpdateService._verify_app_sha256(zip_path, "https://example.com/bad.zip")
        assert not os.path.exists(zip_path)

    def test_404_sidecar_skips(self, tmp_path):
        from src.services.installer.app_update_service import AppUpdateService

        zip_path = str(tmp_path / "ok.zip")
        with open(zip_path, "wb") as f:
            f.write(b"data")

        resp = Mock(status_code=404)
        with patch("requests.get", return_value=resp):
            assert AppUpdateService._verify_app_sha256(zip_path, "https://example.com/update.zip")
        assert os.path.exists(zip_path)

    def test_network_error_on_sidecar_skips(self, tmp_path):
        """Network failure fetching .dgst should not block update."""
        from src.services.installer.app_update_service import AppUpdateService

        zip_path = str(tmp_path / "ok.zip")
        with open(zip_path, "wb") as f:
            f.write(b"data")

        with patch("requests.get", side_effect=Exception("timeout")):
            assert AppUpdateService._verify_app_sha256(zip_path, "https://example.com/update.zip")
