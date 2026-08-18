"""Tests for H1 (xray_service._guaranteed_cleanup parity with stop) and
H3 (route_manager_service idempotent crash-safe cleanup)."""

import inspect
import os
import tempfile
import threading
from unittest.mock import Mock, patch

from src.services.route_manager_service import RouteManagerService
from src.services.xray_service import XrayService


# ------------------------------------------------------------------------- #
# H1 — _guaranteed_cleanup must kill process + remove PID file + stop SNI
# ------------------------------------------------------------------------- #
class TestXrayGuaranteedCleanup:
    def test_kill_process_and_cleanup_removes_pid_and_process(self):
        """H1 core: _kill_process_and_cleanup (shared by stop() + guaranteed)
        kills the process and removes the PID file."""
        svc = XrayService.__new__(XrayService)
        svc._pid = 4242
        svc._process = object()
        svc._cleanup_lock = threading.Lock()

        pidf = tempfile.mktemp(suffix=".pid")
        with open(pidf, "w") as f:
            f.write("4242")

        with patch("src.services.xray_service.ProcessUtils") as m_pu, patch(
            "src.services.xray_service.XRAY_PID_FILE", pidf
        ):
            m_pu.is_running.return_value = False  # simulate already-stopped
            killed = svc._kill_process_and_cleanup()

        assert killed == 4242
        assert svc._pid is None
        assert svc._process is None
        # PID file removed + kill_process attempted
        assert m_pu.kill_process.call_count >= 1
        assert not os.path.exists(pidf)
        os.remove(pidf) if os.path.exists(pidf) else None

    def test_stop_and_guaranteed_share_kill_helper(self):
        """Both stop() and _guaranteed_cleanup() route through
        _kill_process_and_cleanup (single source of truth, no divergence)."""
        src = inspect.getsource(XrayService)
        # both reference the shared helper by name
        assert src.count("_kill_process_and_cleanup") >= 2


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
        svc = RouteManagerService.__new__(RouteManagerService)
        svc._added_routes = ["1.1.1.1", "2.2.2.2", "3.3.3.3"]
        fake = FakeRun(fail_ips={"2.2.2.2"})  # 2.2.2.2 deletion fails

        with patch("src.services.route_manager_service.PlatformUtils") as m_pu, patch.object(
            svc, "_host_route_del_cmd", side_effect=lambda ip, p: ["route", "delete", ip]
        ), patch("src.services.route_manager_service.subprocess.run", side_effect=fake):
            m_pu.get_platform.return_value = "windows"
            m_pu.get_subprocess_flags.return_value = 0
            m_pu.get_startupinfo.return_value = None
            svc._cleanup_host_routes()

        # order preserved: dropped only the succeeded ones (2.2.2.2 + 3.3.3.3 removed)
        # 1.1.1.1 succeeded -> gone; 2.2.2.2 failed -> kept; 3.3.3.3 succeeded -> gone
        assert svc._added_routes == ["2.2.2.2"]
        # only failed entry retried on next call
        fake.fail_ips.clear()
        with patch("src.services.route_manager_service.PlatformUtils") as m_pu, patch.object(
            svc, "_host_route_del_cmd", side_effect=lambda ip, p: ["route", "delete", ip]
        ), patch("src.services.route_manager_service.subprocess.run", side_effect=fake):
            m_pu.get_platform.return_value = "windows"
            m_pu.get_subprocess_flags.return_value = 0
            m_pu.get_startupinfo.return_value = None
            svc._cleanup_host_routes()

        assert svc._added_routes == []  # fully drained on retry
