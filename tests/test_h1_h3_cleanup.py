"""Tests for H1 (xray_service._guaranteed_cleanup parity with stop) and
H3 (route_manager_service idempotent crash-safe cleanup)."""

import inspect
import os
import tempfile
from unittest.mock import Mock, patch

from src.services.connection.route_manager_service import RouteManagerService
from src.services.core_engines.xray_process_manager import XrayProcessManager
from src.services.core_engines.xray_service import XrayService


# ------------------------------------------------------------------------- #
# H1 — _guaranteed_cleanup must kill process + remove PID file + stop SNI
# ------------------------------------------------------------------------- #
class TestXrayGuaranteedCleanup:
    def test_kill_process_and_cleanup_removes_pid_and_process(self):
        """H1 core: the process manager's kill_and_cleanup (shared by stop() and
        guaranteed teardown) kills the process and removes the PID file."""
        mgr = XrayProcessManager.__new__(XrayProcessManager)
        mgr._pid = 4242
        mgr._process = object()

        pidf = tempfile.mktemp(suffix=".pid")
        with open(pidf, "w") as f:
            f.write("4242")

        with patch("src.services.core_engines.xray_process_manager.ProcessUtils") as m_pu, patch(
            "src.services.core_engines.xray_process_manager.XRAY_PID_FILE", pidf
        ):
            m_pu.is_running.return_value = False  # simulate already-stopped
            killed = mgr.kill_and_cleanup()

        assert killed == 4242
        assert mgr._pid is None
        assert mgr._process is None
        # PID file removed + kill_process attempted
        assert m_pu.kill_process.call_count >= 1
        assert not os.path.exists(pidf)
        os.remove(pidf) if os.path.exists(pidf) else None

    def test_stop_and_guaranteed_share_kill_helper(self):
        """Both stop() and _guaranteed_cleanup() route through the process
        manager's kill_and_cleanup (single source of truth, no divergence)."""
        svc_src = inspect.getsource(XrayService)
        mgr_src = inspect.getsource(XrayProcessManager)
        # facade's stop() + _guaranteed_cleanup() both call kill_and_cleanup
        assert svc_src.count("kill_and_cleanup") >= 2
        # the actual implementation lives in the process manager
        assert "def kill_and_cleanup" in mgr_src


# ------------------------------------------------------------------------- #
# H3 — cleanup keeps failed removals tracked (crash-safe idempotency)
# ------------------------------------------------------------------------- #
class FakeRun:
    def __init__(self, fail_ips):
        self.fail_ips = set(fail_ips)
        self.calls = {}

    def __call__(self, cmd, **kwargs):
        ip = cmd[-1]
        self.calls[ip] = self.calls.get(ip, 0) + 1
        # simulate a failing subprocess result
        res = Mock()
        res.returncode = 1 if ip in self.fail_ips else 0
        return res


class TestRouteCleanupIdempotent:
    def test_failed_host_route_removal_is_retried(self):
        mock_adapter = Mock()
        mock_adapter.delete_host_route.side_effect = lambda ip: ip != "2.2.2.2"

        svc = RouteManagerService(route_adapter=mock_adapter)
        svc._added_routes = ["1.1.1.1", "2.2.2.2", "3.3.3.3"]

        svc._cleanup_host_routes()

        # 1.1.1.1 succeeded -> gone; 2.2.2.2 failed -> kept; 3.3.3.3 succeeded -> gone
        assert svc._added_routes == ["2.2.2.2"]

        # only failed entry retried on next call
        mock_adapter.delete_host_route.side_effect = lambda ip: True
        svc._cleanup_host_routes()

        assert svc._added_routes == []  # fully drained on retry
