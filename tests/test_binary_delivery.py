"""Offline unit and integration tests for core binary delivery and packaging validation.

Verifies:
1. scripts/download_binaries.py picks up pinned XRAY_VERSION constant (26.10.31).
2. URL generation matches upstream release structure.
3. Strict fail-closed SHA-256 sidecar checksum validation (.dgst, HTTP 404/500, malformed, empty).
4. Pinned checksum verification for assets without dedicated sidecars.
5. Strict fail-closed archive member extraction (FileNotFoundError on missing member).
6. build_pyinstaller.py:ensure_core_binaries() fail-closed guards against missing, unexecutable,
   or mismatched binaries and assets.
"""

import hashlib
import subprocess
import urllib.error
import zipfile
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
    expected_sha = hashlib.sha256(dummy_content).hexdigest()
    sidecar_data = f"SHA2-512=abc\nSHA2-256={expected_sha}\nMD5=xyz".encode("utf-8")

    dest = tmp_path / "test.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = sidecar_data
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda url, timeout: mock_resp)

    out_path = downloader.download_file("https://example.com/test.zip", dest, require_dgst=True)
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
    mock_resp.status = 200
    mock_resp.read.return_value = sidecar_data
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda url, timeout: mock_resp)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/corrupt.zip", dest, require_dgst=True)

    assert "SHA-256 mismatch" in str(exc_info.value)
    assert not dest.exists()


def test_download_file_fails_when_sidecar_missing_404_for_xray(tmp_path, monkeypatch):
    """HTTP 404 for required sidecar must delete destination archive and raise RuntimeError."""
    dummy_content = b"unverified binary content"
    dest = tmp_path / "xray.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    def mock_urlopen(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", mock_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/xray.zip", dest, require_dgst=True)

    assert "HTTP 404" in str(exc_info.value)
    assert not dest.exists()


def test_download_file_fails_when_sidecar_http_500(tmp_path, monkeypatch):
    """HTTP 500 for required sidecar must delete destination archive and raise RuntimeError."""
    dummy_content = b"unverified binary content"
    dest = tmp_path / "xray.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    def mock_urlopen(url, timeout):
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", mock_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/xray.zip", dest, require_dgst=True)

    assert "HTTP 500" in str(exc_info.value)
    assert not dest.exists()


def test_download_file_fails_when_sidecar_network_urlerror(tmp_path, monkeypatch):
    """Network connection failure fetching sidecar must delete archive and fail-closed."""
    dummy_content = b"unverified binary content"
    dest = tmp_path / "xray.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    def mock_urlopen(url, timeout):
        raise urllib.error.URLError("Connection reset by peer")

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", mock_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/xray.zip", dest, require_dgst=True)

    assert "Network error" in str(exc_info.value)
    assert not dest.exists()


def test_download_file_fails_when_sidecar_has_empty_checksum(tmp_path, monkeypatch):
    """Sidecar without SHA2-256 line must result in hard failure and unlinked archive."""
    dummy_content = b"unverified binary content"
    dest = tmp_path / "xray.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"MD5=123\nSHA1=456"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda url, timeout: mock_resp)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/xray.zip", dest, require_dgst=True)

    assert "Missing required SHA2-256" in str(exc_info.value)
    assert not dest.exists()


def test_download_file_fails_when_sidecar_has_malformed_checksum(tmp_path, monkeypatch):
    """Sidecar with invalid length or non-hex characters must be rejected immediately."""
    dummy_content = b"unverified binary content"
    dest = tmp_path / "xray.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"SHA2-256=not-a-valid-hex-digest-too-short"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda url, timeout: mock_resp)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/xray.zip", dest, require_dgst=True)

    assert "Malformed SHA-256 digest" in str(exc_info.value)
    assert not dest.exists()


def test_download_file_verifies_pinned_checksum_success(tmp_path, monkeypatch):
    """Assets with pinned checksum (e.g. Wintun) verify successfully when matching."""
    dummy_content = b"trusted wintun content"
    expected_sha = hashlib.sha256(dummy_content).hexdigest()
    dest = tmp_path / "wintun-0.14.1.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)

    out = downloader.download_file("https://example.com/wintun.zip", dest, expected_sha256=expected_sha)
    assert out.exists()


def test_download_file_verifies_pinned_checksum_mismatch_fails(tmp_path, monkeypatch):
    """Assets with pinned checksum abort and remove archive when mismatch occurs."""
    dummy_content = b"corrupted wintun content"
    wrong_sha = "1111111111111111111111111111111111111111111111111111111111111111"
    dest = tmp_path / "wintun-0.14.1.zip"

    def mock_urlretrieve(url, filename, reporthook=None):
        Path(filename).write_bytes(dummy_content)

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", mock_urlretrieve)

    with pytest.raises(RuntimeError) as exc_info:
        downloader.download_file("https://example.com/wintun.zip", dest, expected_sha256=wrong_sha)

    assert "SHA-256 mismatch" in str(exc_info.value)
    assert not dest.exists()


def test_extract_zip_extracts_required_member_successfully(tmp_path):
    """extract_zip successfully extracts requested member and returns final path."""
    zip_path = tmp_path / "test_archive.zip"
    extract_dir = tmp_path / "output_bin"
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("xray.exe", "fake binary executable")
        z.writestr("geoip.dat", "fake geoip")

    result = downloader.extract_zip(zip_path, extract_dir, "xray.exe")
    assert result == extract_dir / "xray.exe"
    assert (extract_dir / "xray.exe").read_text() == "fake binary executable"


def test_extract_zip_fails_when_required_member_missing(tmp_path):
    """Missing required target in archive raises FileNotFoundError fail-closed."""
    zip_path = tmp_path / "incomplete_archive.zip"
    extract_dir = tmp_path / "output_bin"
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("some_other_file.txt", "content")

    with pytest.raises(FileNotFoundError) as exc_info:
        downloader.extract_zip(zip_path, extract_dir, "xray.exe")

    assert "Required member 'xray.exe' not found" in str(exc_info.value)


def test_extract_zip_fails_when_archive_does_not_exist(tmp_path):
    """Non-existent archive path raises FileNotFoundError."""
    missing_zip = tmp_path / "non_existent.zip"
    extract_dir = tmp_path / "output_bin"

    with pytest.raises(FileNotFoundError) as exc_info:
        downloader.extract_zip(missing_zip, extract_dir, "xray.exe")

    assert "Archive not found" in str(exc_info.value)


def test_ensure_core_binaries_skips_non_windows(monkeypatch):
    """On non-Windows platforms, ensure_core_binaries is a no-op."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Linux")
    mock_exit_called = []
    monkeypatch.setattr(build_pyinstaller.sys, "exit", lambda code: mock_exit_called.append(code))

    build_pyinstaller.ensure_core_binaries()
    assert len(mock_exit_called) == 0


def test_ensure_core_binaries_triggers_downloader_when_missing(monkeypatch, tmp_path):
    """When bin/xray.exe is missing, ensure_core_binaries invokes downloader and checks version."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    xray_exe = bin_dir / "xray.exe"
    (bin_dir / "geoip.dat").write_text("geo")
    (bin_dir / "geosite.dat").write_text("geo")

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
    (bin_dir / "geoip.dat").write_text("geo")
    (bin_dir / "geosite.dat").write_text("geo")

    def fake_check_output(cmd, **kwargs):
        return "Xray 26.10.17 (Xray, Penetrates Everything.)\n"

    monkeypatch.setattr(build_pyinstaller.subprocess, "check_output", fake_check_output)

    with pytest.raises(SystemExit) as exc_info:
        build_pyinstaller.ensure_core_binaries()

    assert exc_info.value.code == 1


def test_ensure_core_binaries_aborts_on_version_command_calledprocesserror(monkeypatch, tmp_path):
    """When xray.exe version exits with non-zero code, packaging aborts fail-closed."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    xray_exe = bin_dir / "xray.exe"
    xray_exe.write_text("corrupted binary")
    (bin_dir / "geoip.dat").write_text("geo")
    (bin_dir / "geosite.dat").write_text("geo")

    def fake_check_output(cmd, **kwargs):
        raise subprocess.CalledProcessError(returncode=127, cmd=cmd, output="Crash")

    monkeypatch.setattr(build_pyinstaller.subprocess, "check_output", fake_check_output)

    with pytest.raises(SystemExit) as exc_info:
        build_pyinstaller.ensure_core_binaries()

    assert exc_info.value.code == 1


def test_ensure_core_binaries_aborts_on_version_command_exception(monkeypatch, tmp_path):
    """When executing xray.exe throws an unexpected OS error, packaging aborts fail-closed."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    xray_exe = bin_dir / "xray.exe"
    xray_exe.write_text("corrupted binary")
    (bin_dir / "geoip.dat").write_text("geo")
    (bin_dir / "geosite.dat").write_text("geo")

    def fake_check_output(cmd, **kwargs):
        raise OSError("Exec format error / incompatible binary architecture")

    monkeypatch.setattr(build_pyinstaller.subprocess, "check_output", fake_check_output)

    with pytest.raises(SystemExit) as exc_info:
        build_pyinstaller.ensure_core_binaries()

    assert exc_info.value.code == 1


def test_ensure_core_binaries_aborts_when_xray_missing_after_staging(monkeypatch, tmp_path):
    """If staging runs but xray.exe remains missing, packaging aborts fail-closed."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)

    def fake_download_main(args=None):
        return 0  # Claims success without producing binary

    monkeypatch.setattr(downloader, "main", fake_download_main)

    with pytest.raises(SystemExit) as exc_info:
        build_pyinstaller.ensure_core_binaries()

    assert exc_info.value.code == 1


def test_ensure_core_binaries_aborts_when_assets_missing(monkeypatch, tmp_path):
    """If xray.exe is present but geoip.dat or geosite.dat is missing, packaging aborts."""
    monkeypatch.setattr(build_pyinstaller.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_pyinstaller, "PROJECT_ROOT", str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "xray.exe").write_text("valid binary")
    # Missing geoip.dat and geosite.dat

    with pytest.raises(SystemExit) as exc_info:
        build_pyinstaller.ensure_core_binaries()

    assert exc_info.value.code == 1
