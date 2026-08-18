"""Tests for the transparent-relay SNI-spoof design.

Covers:
  - physical-NIC selection (and safe fallback) in listener.py
  - injector driver-failure handling (on_fail callback)
  - listener.configure / SniSpoofService.start apply persisted config
"""

import sys
from unittest.mock import Mock, patch

from src.services.sni_spoof import listener as listener_mod
from src.services.sni_spoof import sni_spoof_service as svc_mod
from src.services.sni_spoof.sni_spoof_service import SniSpoofService
from src.services.sni_spoof.tcp_injector import FakeTcpInjector


class FakeRepo:
    def get_sni_fake_sni(self):
        return "fake.example.com"

    def get_sni_connect_ip(self):
        return "10.0.0.2"

    def get_sni_connect_port(self):
        return 8443

    def get_sni_listen_host(self):
        return "0.0.0.0"

    def get_sni_listen_port(self):
        return 44443


# --------------------------------------------------------------------------- #
# Physical NIC selection falls back safely
# --------------------------------------------------------------------------- #


def test_get_physical_nic_uses_os_default_egress(monkeypatch):
    # OS Default-Route Discovery wins: the dummy-UDP egress IP is the primary NIC,
    # and the interface name is derived from a psutil IP match.
    monkeypatch.setattr(listener_mod, "_os_default_egress_ip", lambda: "192.168.70.125")

    def _fake_addrs():
        return {
            "Ethernet 2": [
                type(
                    "A",
                    (),
                    {
                        "family": listener_mod.socket.AF_INET,
                        "address": "192.168.70.125",
                    },
                )()
            ],
            "Wi-Fi": [
                type(
                    "A",
                    (),
                    {"family": listener_mod.socket.AF_INET, "address": "10.0.0.5"},
                )()
            ],
        }

    monkeypatch.setattr("psutil.net_if_addrs", _fake_addrs)
    assert listener_mod.get_physical_nic_ip() == "192.168.70.125"


def test_get_physical_nic_falls_back_to_route_table(monkeypatch):
    # If OS egress fails, the route-table primary interface is used.
    monkeypatch.setattr(listener_mod, "_os_default_egress_ip", lambda: "")
    monkeypatch.setattr(
        "src.utils.network_interface.NetworkInterfaceDetector.get_primary_interface",
        lambda: ("Ethernet 2", "192.168.70.125", "192.168.70.0/24", "192.168.70.1"),
    )
    assert listener_mod.get_physical_nic_ip() == "192.168.70.125"


def test_get_physical_nic_ip_last_resort_fallback(monkeypatch):
    monkeypatch.setattr(listener_mod, "_os_default_egress_ip", lambda: "")
    monkeypatch.setattr(
        "src.utils.network_interface.NetworkInterfaceDetector.get_primary_interface",
        lambda: (None, None, None, None),
    )
    monkeypatch.setattr(listener_mod, "_blacklist_scan_ip", lambda: "")
    monkeypatch.setattr(
        listener_mod, "get_default_interface_ipv4", lambda: "203.0.113.55"
    )
    assert listener_mod.get_physical_nic_ip() == "203.0.113.55"


def test_os_default_egress_ip(monkeypatch):
    fake = Mock()
    fake.getsockname.return_value = ("9.9.9.9", 0)
    monkeypatch.setattr(listener_mod.socket, "socket", lambda *a, **k: fake)
    assert listener_mod._os_default_egress_ip() == "9.9.9.9"


def test_skip_virtual_iface_rejects_vethernet():
    assert listener_mod._skip_virtual_iface("vEthernet (Default Switch)")
    assert listener_mod._skip_virtual_iface("WSL")
    assert not listener_mod._skip_virtual_iface("Ethernet 2")
    assert not listener_mod._skip_virtual_iface("Wi-Fi")


def test_resolve_connect_ipv4_keeps_numeric():
    assert listener_mod.resolve_connect_ipv4("185.193.30.94") == "185.193.30.94"


def test_resolve_connect_ipv4_resolves_domain(monkeypatch):
    monkeypatch.setattr(listener_mod.socket, "gethostbyname", lambda host: "104.18.1.2")
    assert listener_mod.resolve_connect_ipv4("chess.com") == "104.18.1.2"


def test_serve_survives_accept_oserror_and_exits_on_closed_socket():
    import asyncio as _asyncio

    async def _run():
        loop = _asyncio.get_running_loop()
        calls = {"n": 0}

        async def _boom(sock, *a, **k):
            calls["n"] += 1
            raise OSError(64, "network name deleted")

        loop.sock_accept = _boom  # override accept on the running loop instance
        fake = Mock()
        fake.fileno.return_value = -1  # socket already closed → serve returns cleanly
        await listener_mod.serve(fake)
        assert calls["n"] == 1

    _asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Injector driver-failure handling (option C)
# --------------------------------------------------------------------------- #


def test_injector_run_calls_on_fail_when_pydivert_missing():
    on_fail = Mock()
    fixture = FakeTcpInjector("tcp", {})
    with patch.dict(sys.modules, {"pydivert": None}):
        result = fixture.run(on_fail=on_fail)
    assert result is False
    on_fail.assert_called_once()


def test_injector_run_calls_on_fail_on_driver_open_error():
    on_fail = Mock()
    fixture = FakeTcpInjector("tcp", {})

    class _Boom:
        def __init__(self, *a, **k):
            raise OSError("driver open failed")

    class _FakePydivert:
        WinDivert = _Boom

    with patch.dict(sys.modules, {"pydivert": _FakePydivert()}):
        result = fixture.run(on_fail=on_fail)
    assert result is False
    on_fail.assert_called_once()


# --------------------------------------------------------------------------- #
# Configure / start apply persisted config
# --------------------------------------------------------------------------- #


def test_configure_sets_transparent_relay_fields():
    listener_mod.configure(
        {
            "FAKE_SNI": "x.com",
            "CONNECT_IP": "203.0.113.7",
            "CONNECT_PORT": 8443,
            "LISTEN_HOST": "0.0.0.0",
            "LISTEN_PORT": 7777,
        }
    )
    assert listener_mod.FAKE_SNI == "x.com"
    assert listener_mod.CONNECT_IP == "203.0.113.7"
    assert listener_mod.CONNECT_PORT == 8443
    assert listener_mod.LISTEN_HOST == "0.0.0.0"
    assert listener_mod.LISTEN_PORT == 7777


class _DiskRepo:
    def get_sni_connect_ip(self):
        return "10.0.0.2"

    def get_sni_connect_port(self):
        return 8443


def test_start_applies_dynamic_config_and_runs_listener(monkeypatch):
    monkeypatch.setattr(
        "src.repositories.settings_repository.SettingsRepository",
        lambda *a, **k: _DiskRepo(),
    )
    service = SniSpoofService(settings_repo=FakeRepo())
    try:
        with (
            patch.object(svc_mod, "_prerequisites_ok", return_value=(True, "")),
            patch.object(svc_mod, "run_listener"),
            patch.object(svc_mod, "configure") as m_conf,
        ):
            assert service.start() is True
        m_conf.assert_called_once()
        cfg = m_conf.call_args.args[0]
        assert cfg["FAKE_SNI"] == "fake.example.com"
        assert cfg["CONNECT_IP"] == "10.0.0.2"
        assert cfg["CONNECT_PORT"] == 8443
        assert cfg["LISTEN_HOST"] == "0.0.0.0"
        assert cfg["LISTEN_PORT"] == 44443
    finally:
        service.stop()
