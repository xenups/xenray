"""SNI Spoof service fail-soft tests (non-admin / missing pydivert)."""

import builtins
import sys
from unittest.mock import patch

from src.services.sni_spoof import sni_spoof_service as svc_mod
from src.services.sni_spoof.sni_spoof_service import (
    STATUS_FAILED,
    STATUS_STOPPED,
    SniSpoofService,
)


class FakeRepo:
    def get_sni_spoof_enabled(self):
        return True

    def get_sni_connect_ip(self):
        return "185.193.30.94"

    def get_sni_connect_port(self):
        return 443

    def get_sni_listen_host(self):
        return "127.0.0.1"

    def get_sni_listen_port(self):
        return 40443

    def get_sni_fake_sni(self):
        return "chatgpt.com"


def test_prerequisites_reject_non_admin():
    """Non-admin must be refused (WinDivert kernel driver needs elevation).

    pydivert is stubbed into sys.modules so the check deterministically reaches
    the admin branch regardless of whether pydivert is installed in the env.
    """
    with (
        patch.dict(sys.modules, {"pydivert": object()}),
        patch.object(svc_mod.ProcessUtils, "is_admin", return_value=False),
    ):
        ok, reason = svc_mod._prerequisites_ok()
        assert ok is False
        assert "administrator" in reason.lower()


def test_prerequisites_reject_missing_pydivert():
    """Missing pydivert must be refused even when admin."""
    real_import = builtins.__import__

    def _block_pydivert(name, *args, **kwargs):
        if name == "pydivert":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    with (
        patch.object(svc_mod.ProcessUtils, "is_admin", return_value=True),
        patch.object(builtins, "__import__", side_effect=_block_pydivert),
    ):
        ok, reason = svc_mod._prerequisites_ok()
    assert ok is False
    assert "pydivert" in reason.lower()


def test_start_returns_false_and_does_not_raise_when_not_ok():
    """start() must return False + failed status (never raise) when prerequisites missing."""
    svc = SniSpoofService(settings_repo=FakeRepo())
    with patch.object(svc_mod, "_prerequisites_ok", return_value=(False, "blocked")):
        result = svc.start()  # must not raise
    assert result is False
    assert svc.status == STATUS_FAILED
    assert svc.running is False


def test_stop_is_safe_when_never_started():
    """stop() on an unstarted service must not raise."""
    svc = SniSpoofService(settings_repo=FakeRepo())
    svc.stop()
    assert svc.status == STATUS_STOPPED
