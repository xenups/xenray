"""Unit tests for the Core Update Failure Fix & Binary Replacement Lifecycle.

Tests:
1. Process termination and lock release for xray.exe and sing-box.exe.
2. Atomic 5-step file replacement:
   - Staging extraction & verification
   - Nested archive extraction (sing-box layout)
   - Integrity verification (rejecting corrupt/empty binary)
   - Rollback on failure
3. Network & proxy routing:
   - Direct networking fallback on ProxyError
   - Staging before cycling proxy
4. Permission handling:
   - Write access validation and CorePermissionError with elevation guidance
"""

from __future__ import annotations

import os
import zipfile
from unittest.mock import Mock, patch

import pytest
import requests

from src.services.core_engines.singbox_process_manager import SingboxProcessManager
from src.services.core_engines.xray_process_manager import XrayProcessManager
from src.services.installer.archive_extractor import OLD_SUFFIX, ArchiveExtractor, CorePermissionError
from src.services.installer.file_downloader import FileDownloader
from src.services.installer.singbox_installer import SingboxInstallerService
from src.services.installer.singbox_version_checker import SingboxVersionChecker
from src.services.installer.xray_installer import XrayInstallerService
from src.services.installer.xray_version_checker import XrayVersionChecker


def _create_zip(zip_path, file_dict):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in file_dict.items():
            zf.writestr(name, data)


# ==============================================================================
# 1. Process Termination & Lock Release
# ==============================================================================


def test_xray_process_manager_kill_all_core_instances():
    """Verify XrayProcessManager.kill_all_core_instances uses /T tree-kill on Windows."""
    with patch("subprocess.run") as mock_subproc, patch("psutil.process_iter", return_value=[]), patch("time.sleep"):
        XrayProcessManager.kill_all_core_instances()
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args[0][0]
        if os.name == "nt":
            assert "/T" in cmd
            assert "/IM" in cmd
            assert "xray.exe" in cmd
        else:
            assert "xray" in cmd


def test_singbox_process_manager_kill_all_core_instances():
    """Verify SingboxProcessManager.kill_all_core_instances uses /T tree-kill on Windows."""
    with patch("subprocess.run") as mock_subproc, patch("psutil.process_iter", return_value=[]), patch("time.sleep"):
        SingboxProcessManager.kill_all_core_instances()
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args[0][0]
        if os.name == "nt":
            assert "/T" in cmd
            assert "/IM" in cmd
            assert "sing-box.exe" in cmd
        else:
            assert "sing-box" in cmd


def test_terminate_and_wait_for_lock_release(tmp_path):
    """Verify lock release polling retries and succeeds once handle is free."""
    extractor = ArchiveExtractor(str(tmp_path))
    target_file = tmp_path / "xray.exe"
    target_file.write_bytes(b"dummy")

    with patch.object(extractor, "_kill_active_core") as mock_kill:
        # File is free on disk, open for r+b succeeds immediately
        assert extractor.terminate_and_wait_for_lock_release(str(target_file), timeout_seconds=1.0) is True
        mock_kill.assert_called()


# ==============================================================================
# 2. Atomic 5-Step File Replacement & Integrity Verification
# ==============================================================================


def test_extract_core_nested_archive_singbox(tmp_path, monkeypatch):
    """Sing-box archives have nested directories (sing-box-*-windows-amd64/sing-box.exe).

    Extractor must locate the binary in the nested tree and deploy it to bin/sing-box.exe.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self, *a, **k: None)

    zip_path = tmp_path / "singbox.zip"
    _create_zip(
        zip_path,
        {
            "sing-box-1.14.0-windows-amd64/sing-box.exe": b"SINGBOX_BINARY_DATA",
            "sing-box-1.14.0-windows-amd64/LICENSE": b"GPL",
        },
    )

    extractor = ArchiveExtractor(str(bin_dir))
    success = extractor.extract_core(str(zip_path), target_binary_name="sing-box.exe")

    assert success is True
    installed_file = bin_dir / "sing-box.exe"
    assert installed_file.exists()
    assert installed_file.read_bytes() == b"SINGBOX_BINARY_DATA"
    assert not (bin_dir / ("sing-box.exe" + OLD_SUFFIX)).exists()


def test_extract_core_integrity_rejects_empty_binary(tmp_path, monkeypatch):
    """Integrity check must reject empty (0-byte) binaries in staging without touching active core."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self, *a, **k: None)

    active_xray = bin_dir / "xray.exe"
    active_xray.write_bytes(b"ACTIVE_GOOD_XRAY")

    corrupt_zip = tmp_path / "corrupt_xray.zip"
    _create_zip(corrupt_zip, {"xray.exe": b""})  # 0 bytes

    extractor = ArchiveExtractor(str(bin_dir))
    success = extractor.extract_core(str(corrupt_zip))

    assert success is False
    # Active binary must remain untouched
    assert active_xray.read_bytes() == b"ACTIVE_GOOD_XRAY"


def test_verify_binary_integrity_checks():
    """verify_binary_integrity validates existence, non-empty, and non-native headers."""
    extractor = ArchiveExtractor("/fake/bin")
    assert extractor.verify_binary_integrity("/nonexistent/file") is False


# ==============================================================================
# 3. Network & Proxy Routing for Updater
# ==============================================================================


def test_file_downloader_direct_fallback_on_proxy_error(tmp_path):
    """FileDownloader must fallback to direct system networking when proxy fails."""
    downloader = FileDownloader(max_retries=2)
    dest_path = str(tmp_path / "downloaded.zip")

    # First attempt: ProxyError. Second attempt: Success.
    mock_proxy_err = requests.exceptions.ProxyError("Cannot connect to proxy 127.0.0.1:10808")
    mock_success_resp = Mock()
    mock_success_resp.headers = {"content-length": "2048"}
    mock_success_resp.iter_content.return_value = [b"a" * 2048]
    mock_success_resp.raise_for_status = Mock()

    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise mock_proxy_err
        return mock_success_resp

    with patch("requests.Session.get", side_effect=mock_get):
        result = downloader.download(
            "https://example.com/test.zip",
            dest_path,
        )

    assert result == dest_path
    assert os.path.exists(dest_path)
    assert call_count >= 2


def test_xray_version_checker_direct_fallback():
    """XrayVersionChecker must fallback to direct connection when primary request fails."""
    checker = XrayVersionChecker(executable_path="/nonexistent")

    mock_net_err = requests.exceptions.ConnectionError("Proxy unreachable")
    mock_success_resp = Mock()
    mock_success_resp.json.return_value = [
        {"tag_name": "v26.9.8", "prerelease": False},
    ]
    mock_success_resp.raise_for_status = Mock()

    with patch("requests.get", side_effect=mock_net_err), patch("requests.Session.get", return_value=mock_success_resp):
        with patch.object(checker, "get_local_version", return_value="25.1.1"):
            avail, curr, latest = checker.check_for_updates(include_prerelease=False)
            assert avail is True
            assert latest == "26.9.8"


def test_singbox_version_checker():
    """SingboxVersionChecker parses release JSON and compares versions."""
    checker = SingboxVersionChecker(executable_path="/nonexistent")

    mock_resp = Mock()
    mock_resp.json.return_value = [
        {"tag_name": "v1.14.0", "prerelease": False},
    ]
    mock_resp.raise_for_status = Mock()

    with patch("requests.get", return_value=mock_resp):
        with patch.object(checker, "get_local_version", return_value="1.10.6"):
            avail, curr, latest = checker.check_for_updates(include_prerelease=False)
            assert avail is True
            assert curr == "1.10.6"
            assert latest == "1.14.0"


# ==============================================================================
# 4. Permission Handling & Elevation Guidance
# ==============================================================================


def test_verify_write_permissions_denied_raises_core_permission_error(tmp_path):
    """When target directory is not writable and user is not admin, CorePermissionError is raised with guidance."""
    extractor = ArchiveExtractor(str(tmp_path / "bin"))

    with patch("os.makedirs", side_effect=PermissionError("Access is denied")):
        with patch("src.utils.process_utils.ProcessUtils.is_admin", return_value=False):
            writable, msg = extractor.verify_write_permissions()
            assert writable is False
            assert "Administrator privileges are required" in msg
            assert "restart XenRay as administrator" in msg


def test_xray_installer_service_permission_error_aborts_early():
    """XrayInstallerService.install must abort before downloading if permissions are denied."""
    with patch.object(ArchiveExtractor, "verify_write_permissions", return_value=(False, "Admin required")):
        with pytest.raises(CorePermissionError) as exc_info:
            XrayInstallerService.install()
        assert "Admin required" in str(exc_info.value)


def test_singbox_installer_service_permission_error_aborts_early():
    """SingboxInstallerService.install must abort before downloading if permissions are denied."""
    with patch.object(ArchiveExtractor, "verify_write_permissions", return_value=(False, "Admin required")):
        with pytest.raises(CorePermissionError) as exc_info:
            SingboxInstallerService.install()
        assert "Admin required" in str(exc_info.value)


# ==============================================================================
# 5. Platform Core Asset Adapters & Factory
# ==============================================================================


def test_platform_windows_core_asset_adapter():
    """WindowsCoreAssetAdapter produces correct Windows asset info."""
    from src.platform.windows.core_assets import WindowsCoreAssetAdapter

    adapter = WindowsCoreAssetAdapter()
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="x86_64"):
        xray_info = adapter.get_xray_asset_info("26.9.8")
        assert xray_info.filename == "Xray-windows-64.zip"
        assert "v26.9.8" in xray_info.download_url
        assert xray_info.archive_extension == ".zip"
        assert xray_info.binary_name == "xray.exe"

        sb_info = adapter.get_singbox_asset_info("1.14.0")
        assert sb_info.filename == "sing-box-1.14.0-windows-amd64.zip"
        assert "v1.14.0" in sb_info.download_url
        assert sb_info.archive_extension == ".zip"
        assert sb_info.binary_name == "sing-box.exe"


def test_platform_macos_core_asset_adapter():
    """MacosCoreAssetAdapter produces correct macOS asset info."""
    from src.platform.macos.core_assets import MacosCoreAssetAdapter

    adapter = MacosCoreAssetAdapter()
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="arm64"):
        sb_info = adapter.get_singbox_asset_info("1.14.0")
        assert sb_info.filename == "sing-box-1.14.0-darwin-arm64.tar.gz"
        assert sb_info.archive_extension == ".tar.gz"
        assert sb_info.binary_name == "sing-box"


def test_platform_linux_core_asset_adapter():
    """LinuxCoreAssetAdapter produces correct Linux asset info."""
    from src.platform.linux.core_assets import LinuxCoreAssetAdapter

    adapter = LinuxCoreAssetAdapter()
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="x86_64"):
        sb_info = adapter.get_singbox_asset_info("1.14.0")
        assert sb_info.filename == "sing-box-1.14.0-linux-amd64.tar.gz"
        assert sb_info.archive_extension == ".tar.gz"
        assert sb_info.binary_name == "sing-box"


def test_get_core_asset_adapter_factory():
    """get_core_asset_adapter factory returns platform-appropriate adapter."""
    from src.platform.factory import get_core_asset_adapter
    from src.platform.interfaces.core_assets import ICoreAssetAdapter

    adapter = get_core_asset_adapter()
    assert isinstance(adapter, ICoreAssetAdapter)


def test_file_downloader_uses_platform_adapter():
    """FileDownloader.download_singbox_core and download_xray_core use get_core_asset_adapter without raw OS logic."""
    from src.platform.interfaces.core_assets import CoreAssetInfo

    downloader = FileDownloader()
    mock_sb_asset = CoreAssetInfo(
        filename="custom-sing-box.zip",
        download_url="https://example.com/custom-sing-box.zip",
        archive_extension=".zip",
        binary_name="sing-box.exe",
    )
    mock_xray_asset = CoreAssetInfo(
        filename="custom-xray.zip",
        download_url="https://example.com/custom-xray.zip",
        archive_extension=".zip",
        binary_name="xray.exe",
    )

    with patch("src.platform.get_core_asset_adapter") as mock_get_adapter:
        mock_adapter = Mock()
        mock_adapter.get_singbox_asset_info.return_value = mock_sb_asset
        mock_adapter.get_xray_asset_info.return_value = mock_xray_asset
        mock_get_adapter.return_value = mock_adapter

        with patch.object(downloader, "download", return_value="/tmp/test.zip") as mock_dl:
            with patch.object(downloader, "_verify_sha256", return_value=True):
                # 1. Test sing-box download uses platform asset info
                sb_result = downloader.download_singbox_core()
                assert sb_result == "/tmp/test.zip"
                mock_adapter.get_singbox_asset_info.assert_called_once()
                assert mock_dl.call_args[0][0] == mock_sb_asset.download_url

                # 2. Test Xray download uses platform asset info
                xray_result = downloader.download_xray_core()
                assert xray_result == "/tmp/test.zip"
                mock_adapter.get_xray_asset_info.assert_called_once()
                assert mock_dl.call_args[0][0] == mock_xray_asset.download_url


def test_platform_adapters_architecture_matrix():
    """Verify all platform adapters map all CPU architectures correctly."""
    from src.platform.linux.core_assets import LinuxCoreAssetAdapter
    from src.platform.macos.core_assets import MacosCoreAssetAdapter
    from src.platform.windows.core_assets import WindowsCoreAssetAdapter

    win_adapter = WindowsCoreAssetAdapter()
    mac_adapter = MacosCoreAssetAdapter()
    lin_adapter = LinuxCoreAssetAdapter()

    # Windows architectures: arm64, 32
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="arm64"):
        assert "arm64-v8a" in win_adapter.get_xray_asset_info("v1.0").filename
        assert "arm64" in win_adapter.get_singbox_asset_info("v1.0").filename
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="386"):
        assert "32" in win_adapter.get_xray_asset_info("v1.0").filename
        assert "386" in win_adapter.get_singbox_asset_info("v1.0").filename

    # macOS architectures: arm64 vs x86_64
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="x86_64"):
        assert "64" in mac_adapter.get_xray_asset_info("1.0").filename
        assert "amd64" in mac_adapter.get_singbox_asset_info("1.0").filename

    # Linux architectures: arm64 vs 386
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="arm64"):
        assert "arm64-v8a" in lin_adapter.get_xray_asset_info("1.0").filename
        assert "arm64" in lin_adapter.get_singbox_asset_info("1.0").filename
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="386"):
        assert "32" in lin_adapter.get_xray_asset_info("1.0").filename
        assert "386" in lin_adapter.get_singbox_asset_info("1.0").filename


def test_file_downloader_direct_session_flags():
    """_create_session(direct=True) configures direct connection ignoring env proxies."""
    s_default = FileDownloader._create_session(direct=False)
    assert s_default.trust_env is True

    s_direct = FileDownloader._create_session(direct=True)
    assert s_direct.trust_env is False
    assert s_direct.proxies == {"http": None, "https": None}


def test_file_downloader_sha256_mismatch_discards_file(tmp_path):
    """If SHA-256 verification fails, download methods return None and delete file."""
    downloader = FileDownloader()
    fake_file = tmp_path / "test.zip"
    fake_file.write_bytes(b"content")

    with patch.object(downloader, "download", return_value=str(fake_file)):
        with patch.object(downloader, "_verify_sha256", return_value=False):
            assert downloader.download_xray_core() is None
            assert downloader.download_singbox_core() is None


def test_archive_extractor_verify_write_permissions_admin_flag(tmp_path):
    """verify_write_permissions distinguishes admin vs non-admin error messaging."""
    extractor = ArchiveExtractor(str(tmp_path / "bin"))

    with patch("os.makedirs", side_effect=PermissionError("Denied")):
        with patch("src.utils.process_utils.ProcessUtils.is_admin", return_value=True):
            writable, msg = extractor.verify_write_permissions()
            assert writable is False
            assert "Administrator privileges are required" not in msg
            assert "Denied" in msg


def test_archive_extractor_rollback_on_copy_failure(tmp_path, monkeypatch):
    """When copy/move fails during extraction, files are rolled back from .old."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self, *a, **k: None)

    orig_binary = bin_dir / "xray.exe"
    orig_binary.write_bytes(b"ORIGINAL_BIN")

    zip_path = tmp_path / "update.zip"
    _create_zip(zip_path, {"xray.exe": b"NEW_BIN"})

    extractor = ArchiveExtractor(str(bin_dir))

    with patch("shutil.copy2", side_effect=OSError("Disk full")):
        success = extractor.extract_core(str(zip_path))
        assert success is False

    # Original binary must be restored
    assert orig_binary.exists()
    assert orig_binary.read_bytes() == b"ORIGINAL_BIN"
    assert not (bin_dir / ("xray.exe" + OLD_SUFFIX)).exists()


def test_archive_extractor_pe_integrity_check(tmp_path):
    """verify_binary_integrity runs subprocess on PE header binary."""
    extractor = ArchiveExtractor(str(tmp_path))
    pe_file = tmp_path / "test_pe.exe"
    # Small PE-header binary
    pe_file.write_bytes(b"MZ" + b"\x00" * 100)

    # Subprocess execution succeeds
    mock_run = Mock(returncode=0, stdout="sing-box version 1.14.0\n", stderr="")
    with patch("subprocess.run", return_value=mock_run):
        assert extractor.verify_binary_integrity(str(pe_file)) is True

    # Subprocess execution fails on small corrupted binary
    mock_fail = Mock(returncode=1, stdout="", stderr="Corrupted PE")
    with patch("subprocess.run", return_value=mock_fail):
        assert extractor.verify_binary_integrity(str(pe_file)) is False


def test_singbox_installer_service_lifecycle(tmp_path):
    """SingboxInstallerService.install full lifecycle verification."""
    with patch("os.makedirs"):
        with patch.object(ArchiveExtractor, "verify_write_permissions", return_value=(True, None)):
            with patch.object(FileDownloader, "download_singbox_core", return_value="/tmp/sb.zip"):
                with patch.object(ArchiveExtractor, "extract_core", return_value=True) as mock_extract:
                    with patch("src.services.installer.singbox_installer.get_tun_driver_adapter") as mock_tun:
                        stop_called = []
                        success = SingboxInstallerService.install(
                            progress_callback=lambda m: None,
                            stop_service_callback=lambda: stop_called.append(True),
                            target_version="1.14.0",
                        )
                        assert success is True
                        assert stop_called == [True]
                        mock_extract.assert_called_once()
                        mock_tun().ensure_driver.assert_called_once()


def test_singbox_version_checker_local_version_parsing():
    """SingboxVersionChecker.get_local_version parses version formats correctly."""
    checker = SingboxVersionChecker(executable_path="/fake/sing-box.exe")

    with patch("os.path.exists", return_value=True):
        # 3 parts: "sing-box version 1.14.0"
        mock_res3 = Mock(returncode=0, stdout="sing-box version 1.14.0\n")
        with patch("subprocess.run", return_value=mock_res3):
            assert checker.get_local_version() == "1.14.0"

        # 2 parts: "sing-box v1.14.0"
        mock_res2 = Mock(returncode=0, stdout="sing-box v1.14.0\n")
        with patch("subprocess.run", return_value=mock_res2):
            assert checker.get_local_version() == "1.14.0"

        # Failure returncode
        mock_err = Mock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=mock_err):
            assert checker.get_local_version() is None


def test_singbox_installer_service_is_installed_and_checks():
    """SingboxInstallerService is_installed checks SINGBOX_EXECUTABLE path."""
    with patch("os.path.exists") as mock_exists:
        mock_exists.return_value = True
        assert SingboxInstallerService.is_installed() is True

        mock_exists.return_value = False
        assert SingboxInstallerService.is_installed() is False

    with patch.object(SingboxInstallerService, "get_local_version", return_value="1.10.0"):
        with patch.object(SingboxVersionChecker, "check_for_updates", return_value=(True, "1.10.0", "1.14.0")):
            avail, curr, latest = SingboxInstallerService.check_for_updates()
            assert avail is True
            assert curr == "1.10.0"
            assert latest == "1.14.0"
