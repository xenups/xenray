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
    monkeypatch.setattr(
        "src.platform.windows.network.get_physical_nic_candidates",
        lambda: [],
    )
    monkeypatch.setattr(
        "src.services.sni_spoof.nic_detect.get_physical_nic_candidates",
        lambda: [],
    )
    monkeypatch.setattr(listener_mod, "_os_default_egress_ip", lambda: "192.168.70.125")
    monkeypatch.setattr(listener_mod, "_is_physical_link", lambda iface: True)

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
    monkeypatch.setattr(
        "src.platform.windows.network.get_physical_nic_candidates",
        lambda: [],
    )
    monkeypatch.setattr(
        "src.services.sni_spoof.nic_detect.get_physical_nic_candidates",
        lambda: [],
    )
    monkeypatch.setattr(listener_mod, "_os_default_egress_ip", lambda: "")
    mock_adapter = Mock()
    mock_adapter.get_primary_interface.return_value = (
        "Ethernet 2",
        "192.168.70.125",
        "192.168.70.0/24",
        "192.168.70.1",
    )
    monkeypatch.setattr("src.platform.factory.get_network_adapter", lambda: mock_adapter)
    monkeypatch.setattr(
        "src.utils.network_interface.NetworkInterfaceDetector.get_primary_interface",
        lambda: ("Ethernet 2", "192.168.70.125", "192.168.70.0/24", "192.168.70.1"),
    )
    assert listener_mod.get_physical_nic_ip() == "192.168.70.125"


def test_get_physical_nic_ip_last_resort_fallback(monkeypatch):
    # Force every higher-priority path to yield nothing so we reach the tail.
    monkeypatch.setattr(
        "src.services.sni_spoof.nic_detect.get_physical_nic_candidates",
        lambda: [],
    )
    monkeypatch.setattr(listener_mod, "_os_default_egress_ip", lambda: "")
    monkeypatch.setattr(
        "src.platform.windows.network.WindowsNetworkAdapter.get_primary_interface",
        lambda self: (None, None, None, None),
    )
    monkeypatch.setattr(listener_mod, "_scan_physical_nic_ip", lambda: "")
    monkeypatch.setattr(listener_mod, "get_default_interface_ipv4", lambda: "203.0.113.55")
    assert listener_mod.get_physical_nic_ip() == "203.0.113.55"


def test_os_default_egress_ip(monkeypatch):
    fake = Mock()
    fake.getsockname.return_value = ("9.9.9.9", 0)
    monkeypatch.setattr(listener_mod.socket, "socket", lambda *a, **k: fake)
    assert listener_mod._os_default_egress_ip() == "9.9.9.9"


def test_skip_virtual_iface_replaced_by_iftype():
    """The string-matching name blacklist is gone — physical/virtual is decided
    from the OS link type (IF_TYPE), never from adapter-name keywords."""
    from src.services.sni_spoof.nic_detect import (
        IF_TYPE_ETHERNET_CSMACD,
        IF_TYPE_IEEE80211,
        IF_TYPE_TUNNEL,
        _is_physical_iftype,
    )

    # Physical link types (Ethernet / 802.11) are accepted regardless of name.
    assert _is_physical_iftype(IF_TYPE_ETHERNET_CSMACD)
    assert _is_physical_iftype(IF_TYPE_IEEE80211)
    # Tunnel/VPN link types are NOT physical — this is what replaces the old
    # name-blacklist, and it never depends on the adapter's name/language.
    assert not _is_physical_iftype(IF_TYPE_TUNNEL)
    assert not _is_physical_iftype(0)  # unknown


def test_physical_nic_candidates_filter_by_type_gateway():
    """get_physical_nic_candidates returns only physical+up+IPv4+gateway nics."""
    from src.services.sni_spoof.nic_detect import get_physical_nic_candidates

    cands = get_physical_nic_candidates()
    # Either the API is unavailable (empty) or every candidate is physical/up —
    # a candidate can never be a TUN/TAP (IF_TYPE_TUNNEL is filtered out).
    for c in cands:
        assert c["iftype"] in (6, 71)  # Ethernet/802.11 only
        assert c["operstatus"] == 1  # Up
        assert c["ip"]


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


def _recv_crash_fake(fixture, stop_on_crash: bool):
    stop_flag = fixture._stop_flag

    class _Crash:
        _raised = False

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def recv(self, n):
            if not _Crash._raised:
                _Crash._raised = True
                if stop_on_crash:
                    stop_flag.set()  # teardown signalled while recv was blocked
                raise OSError("WinDivert handle is not open")
            return None

    class _FakePydivert:
        WinDivert = _Crash

    return _FakePydivert()


def test_injector_recv_crash_while_running_calls_on_fail():
    """A recv crash while NOT stopping is a REAL failure → on_fail fires."""
    on_fail = Mock()
    fixture = FakeTcpInjector("tcp", {})
    fake_pyd = _recv_crash_fake(fixture, stop_on_crash=False)
    with patch.dict(sys.modules, {"pydivert": fake_pyd}):
        result = fixture.run(on_fail=on_fail)
    assert result is False
    assert not fixture._stop_flag.is_set()
    on_fail.assert_called_once()


def test_injector_recv_handle_closed_during_teardown_is_graceful():
    """When the WinDivert handle is closed as part of an intentional teardown
    (stop() signals the stop flag + closes the handle while recv is blocked),
    the resulting 'handle is not open' recv error must be a silent graceful exit:
    NEVER call on_fail (which would flip to plain relay + ERROR)."""
    on_fail = Mock()
    fixture = FakeTcpInjector("tcp", {})
    fake_pyd = _recv_crash_fake(fixture, stop_on_crash=True)
    with patch.dict(sys.modules, {"pydivert": fake_pyd}):
        result = fixture.run(on_fail=on_fail)
        assert fixture._stop_flag.is_set()
    assert result is False
    on_fail.assert_not_called()


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
