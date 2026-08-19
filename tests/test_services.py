import json as _json
import threading
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.core.constants import DNS_IP_CLOUDFLARE, DNS_IP_GOOGLE
from src.services.core_engines.xray_service import XrayService


class TestXrayServiceInterface:
    """Tests for XrayService interface contracts (properties vs methods)."""

    def test_is_running_is_property(self):
        """is_running must be a @property (not a method) to prevent 'bool not callable' errors."""
        attr = XrayService.__dict__.get("is_running")
        assert isinstance(attr, property), (
            f"Expected 'is_running' to be a @property, got {type(attr).__name__}. "
            "Access it as attribute, not method: service.is_running (no parentheses)."
        )


class TestXrayService:
    @pytest.fixture
    def xray_service(self):
        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True):
            return XrayService()

    @patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True)
    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_start_success(self, mock_file, mock_isfile, mock_run, mock_is_running, xray_service):
        """Test starting Xray successfully."""
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_run.return_value = mock_proc

        pid = xray_service.start("config.json")

        assert pid == 1234
        assert xray_service.pid == 1234
        mock_run.assert_called_once()
        # Verify PID file was written
        mock_file().write.assert_called_with("1234")

    @patch("src.utils.process_utils.ProcessUtils.kill_process")
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="1234"))
    def test_stop_success(self, mock_exists, mock_kill, xray_service):
        """Test stopping Xray."""
        xray_service._pid = 1234

        with patch("os.remove") as mock_remove:
            assert xray_service.stop() is True
            assert xray_service.pid is None
            mock_kill.assert_called_with(1234, force=False)
            mock_remove.assert_called()

    def _run_windows_tun_start(self, xray_service, tun_dns, mock_run):
        """Start Xray in Windows TUN mode and return the collected subprocess calls."""
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_run.return_value = mock_proc

        fake_cfg = _json.dumps({"inbounds": [{"protocol": "tun", "settings": {"dns": tun_dns}}]})
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return MagicMock(returncode=0)

        with patch("src.platform.factory._is_windows", return_value=True):
            with patch("builtins.open", mock_open(read_data=fake_cfg)):
                with patch("time.sleep", return_value=None):
                    with patch("src.platform.windows.tun_dns.subprocess.run", side_effect=fake_run):
                        pid = xray_service.start("config.json")
                        # TUN DNS is configured in a daemon thread; wait for it so the
                        # recorded netsh commands are complete before asserting.
                        for thread in threading.enumerate():
                            if thread.name == "xenray-tun-dns":
                                thread.join(timeout=10)
        return pid, calls

    @patch("src.utils.platform_utils.PlatformUtils.get_platform", return_value="windows")
    @patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True)
    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("os.path.isfile", return_value=True)
    def test_start_sets_tun_dns_override(self, mock_isfile, mock_run, mock_is_running, mock_platform, xray_service):
        """Windows TUN mode pins primary + secondary DNS on xenray-tun and flushes cache."""
        pid, calls = self._run_windows_tun_start(xray_service, [DNS_IP_CLOUDFLARE, DNS_IP_GOOGLE], mock_run)

        assert pid == 1234
        netsh_cmds = [c for c in calls if c and c[0] == "netsh"]
        assert any(c[3] == "set" and c[6] == "static" and c[7] == DNS_IP_CLOUDFLARE for c in netsh_cmds)
        assert any(c[3] == "add" and c[6] == DNS_IP_GOOGLE and c[7] == "index=2" for c in netsh_cmds)
        assert any(c == ["ipconfig", "/flushdns"] for c in calls)

    @patch("src.utils.platform_utils.PlatformUtils.get_platform", return_value="windows")
    @patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True)
    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("os.path.isfile", return_value=True)
    def test_start_tun_dns_defaults_when_empty(
        self, mock_isfile, mock_run, mock_is_running, mock_platform, xray_service
    ):
        """Empty TUN DNS config falls back to pinned Cloudflare primary + Google secondary."""
        pid, calls = self._run_windows_tun_start(xray_service, [], mock_run)

        assert pid == 1234
        netsh_cmds = [c for c in calls if c and c[0] == "netsh"]
        assert any(c[3] == "set" and c[7] == DNS_IP_CLOUDFLARE for c in netsh_cmds)
        assert any(c[3] == "add" and c[6] == DNS_IP_GOOGLE and c[7] == "index=2" for c in netsh_cmds)

    @patch("src.utils.platform_utils.PlatformUtils.get_platform", return_value="windows")
    @patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True)
    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("os.path.isfile", return_value=True)
    def test_start_tun_dns_dual_stack_sets_ipv6(
        self, mock_isfile, mock_run, mock_is_running, mock_platform, xray_service
    ):
        """Dual-stack TUN DNS pins IPv6 resolver on the adapter via netsh ipv6."""
        ipv6 = "2606:4700:4700::1111"
        pid, calls = self._run_windows_tun_start(xray_service, [DNS_IP_CLOUDFLARE, ipv6], mock_run)

        assert pid == 1234
        netsh_cmds = [c for c in calls if c and c[0] == "netsh"]
        assert any(c[1:4] == ["interface", "ipv6", "set"] and c[7] == ipv6 for c in netsh_cmds)
        # IPv4 DNS still pinned separately
        assert any(c[1:4] == ["interface", "ip", "set"] and c[7] == DNS_IP_CLOUDFLARE for c in netsh_cmds)


class TestDomainServicesPackaging:
    """Verify domain-driven package structure and re-exports."""

    def test_connection_domain_exports(self):
        from src.services.connection import (
            ConnectionOrchestrator,
            ConnectionTester,
            RouteManagerService,
        )

        assert ConnectionOrchestrator is not None
        assert ConnectionTester is not None
        assert RouteManagerService is not None

    def test_core_engines_domain_exports(self):
        from src.services.core_engines import (
            SingboxProcessManager,
            SingboxService,
            XrayConfigProcessor,
            XrayProcessManager,
            XrayService,
        )

        assert XrayService is not None
        assert XrayProcessManager is not None
        assert SingboxService is not None
        assert SingboxProcessManager is not None
        assert XrayConfigProcessor is not None

    def test_installer_domain_exports(self):
        from src.services.installer import (
            AppUpdateService,
            ArchiveExtractor,
            FileDownloader,
            RuleUpdateService,
            XrayInstallerService,
            XrayVersionChecker,
        )

        assert XrayInstallerService is not None
        assert FileDownloader is not None
        assert ArchiveExtractor is not None
        assert XrayVersionChecker is not None
        assert AppUpdateService is not None
        assert RuleUpdateService is not None

    def test_system_domain_exports(self):
        from src.services.system import LanService, is_supported, is_task_registered

        assert LanService is not None
        assert callable(is_task_registered)
        assert callable(is_supported)

    def test_services_root_reexports(self):
        import src.services as svc

        assert hasattr(svc, "ConnectionOrchestrator")
        assert hasattr(svc, "XrayService")
        assert hasattr(svc, "SingboxService")
        assert hasattr(svc, "XrayInstallerService")
        assert hasattr(svc, "ConnectionMonitoringService")
        assert hasattr(svc, "LanService")

    def test_domain_module_imports(self):
        from src.services import XrayService as FacadeXrayService
        from src.services.core_engines.xray_service import XrayService as DomainXrayService

        assert FacadeXrayService is DomainXrayService
