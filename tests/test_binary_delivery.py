"""Offline unit and integration tests for core binary delivery and packaging validation.

Verifies:
1. scripts/download_binaries.py picks up pinned XRAY_VERSION constant (26.10.31).
2. URL generation matches upstream release structure.
3. SHA-256 sidecar checksum validation aborts on hash mismatch.
4. build_pyinstaller.py:ensure_core_binaries() guards packaging against missing or mismatched binaries.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import build_pyinstaller
import scripts.download_binaries as downloader
from src.core.constants import XRAY_VERSION


def test_download_binaries_config_reads_pinned_xray_version(monkeypatch):
    """get_config defaults to pinned XRAY_VERSION constant when env var is absent."""
    monkeypatch.delenv("XRAY_VERSION", raising=False)
    cfg = downloader.get_config(arch=64)

    assert cfg["xray_version"] == XRAY_VERSION
    assert cfg["xray_version"] == "26.10.31"
    assert "v26.10.31/Xray-windows-64.zip" in cfg["xray_url"]


def test_download_binaries_config_honors_env_override(monkeypatch):
    """get_config honors explicit XRAY_VERSION env override when provided."""
    monkeypatch.setenv("XRAY_VERSION", "26.10.99")
    cfg = downloader.get_config(arch=64)

    assert cfg["xray_version"] == "26.10.99"
    assert "v26.10.99/Xray-windows-64.zip" in cfg["xray_url"]


def test_download_file_verifies_sha256_match(tmp_path, monkeypatch):
    """download_file verifies SHA-256 against sidecar and succeeds when match."""
    dummy_content = b"fake binary content for testing"
    import hashlib

    expected_sha = hashlib.sha256(dummy_content).hexdigest()
    sidecar_data = f"SHA2-512=abc\nSHA2-256={expected_sha}\nMD5=xyz".encode("utf-8")

    dest = tmp_path / "test.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    mock_resp = MagicMock()
    mock_resp.read.return_value = sidecar_data
    mock_resp.__enter__.return_value = mock_resp

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda url, timeout: mock_resp)

    out_path = downloader.download_file("https://example.com/test.zip", dest)
    assert out_path.exists()
    assert out_path.read_bytes() == dummy_content


def test_download_file_aborts_on_sha256_mismatch(tmp_path, monkeypatch):
    """download_file deletes destination file and raises RuntimeError on checksum mismatch."""
    dummy_content = b"corrupt binary content"
    wrong_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    sidecar_data = f"SHA2-256={wrong_sha}".encode("utf-8")

    dest = tmp_path / "corrupt.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    mock_resp = MagicMock()
    mock_resp.read.return_value = sidecar_data
    mock_resp.__enter__.return_value = mock_resp

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda url, timeout: mock_resp)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/corrupt.zip", dest)

    assert "SHA-256 mismatch" in str(exc_info.value)
    assert not dest.exists()


def test_ensure_core_binaries_skips_non_windows(monkeypatch):
    """On non-Windows platforms, ensure_core_binaries is a no-op."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Linux")
    mock_exit = MagicMock()
    monkeypatch.setattr(build_pyinstaller.sys, "exit", mock_exit)

    build_pyinstaller.ensure_core_binaries()
    mock_exit.assert_not_called()


def test_ensure_core_binaries_triggers_downloader_when_missing(monkeypatch, tmp_path):
    """When bin/xray.exe is missing, ensure_core_binaries invokes downloader and checks version."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    xray_exe = bin_dir / "xray.exe"

    def fake_download_main(args=None):
        xray_exe.write_text("dummy binary")
        return 0

    monkeypatch.setattr(downloader, "main", fake_download_main)

    def fake_check_output(cmd, **kwargs):
        if cmd[1] == "version":
            return "Xray 26.10.31 (Xray, Penetrates Everything.) a4a3dff\n"
        return ""

    monkeypatch.setattr(build_pyinstaller.subprocess, "check_output", fake_check_output)

    build_pyinstaller.ensure_core_binaries()
    assert xray_exe.exists()


def test_ensure_core_binaries_aborts_on_version_mismatch(monkeypatch, tmp_path):
    """When bin/xray.exe version does not match XRAY_VERSION, build is aborted with sys.exit(1)."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    xray_exe = bin_dir / "xray.exe"
    xray_exe.write_text("old binary")

    def fake_check_output(cmd, **kwargs):
        return "Xray 26.10.17 (Xray, Penetrates Everything.)\n"

    monkeypatch.setattr(build_pyinstaller.subprocess, "check_output", fake_check_output)

    with pytest.raises(SystemExit) as exc_info:
        build_pyinstaller.ensure_core_binaries()

    assert exc_info.value.code == 1
