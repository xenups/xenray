"""TUN-mode DNS-loop guard: the IP-pinning path must actually fire in the real
orchestrator flow (regression guard for the mode-based wiring bug where the code
was green-but-dead: process_mode alias made _uses_singbox_tun return False)."""

from __future__ import annotations

import io
import json
import socket
from unittest.mock import MagicMock

import loguru

from src.services.connection.connection_orchestrator import ConnectionOrchestrator
from src.services.core_engines.xray_config_processor import XrayConfigProcessor


def _server_config(address: str = "1mobility.zenups.ir") -> dict:
    return {
        "inbounds": [],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": address,
                            "port": 443,
                            "users": [{"id": "00000000-0000-0000-0000-000000000000"}],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "tls",
                    "tlsSettings": {"serverName": "4fcb3020-64c0-4e4d-b23b-xenups.ir"},
                },
            }
        ],
    }


def _make_orchestrator() -> ConnectionOrchestrator:
    app_context = MagicMock()
    settings = MagicMock()
    settings.get_tun_engine.return_value = "singbox"
    settings.get_sni_spoof_enabled.return_value = False
    settings.get_proxy_port.return_value = 10805
    settings.get_http_port.return_value = 10809
    settings.get_allow_lan.return_value = False
    settings.get_cipher_suites.return_value = []
    settings.get_routing_country.return_value = ""
    app_context.settings = settings
    routing = MagicMock()
    routing.load_rules.return_value = {"direct": [], "proxy": [], "block": []}
    routing.load_toggles.return_value = {}
    app_context.routing = routing
    net_val = MagicMock()
    xray_proc = XrayConfigProcessor(app_context=app_context)  # REAL processor
    xray_svc = MagicMock()
    xray_svc.start.return_value = 9999  # pretend Xray started
    legacy = MagicMock()
    legacy.is_legacy.return_value = False
    orch = ConnectionOrchestrator(app_context, net_val, xray_proc, xray_svc, legacy)
    orch._singbox_service = MagicMock()
    orch._singbox_service.start.return_value = 12228
    orch._verify_connection_health = MagicMock(return_value=True)
    return orch


def test_tun_flow_pins_outbound_ip_on_disk(tmp_path, monkeypatch):
    # Deterministic DNS: no network in tests.
    def _fake_getaddrinfo(host, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("188.114.99.6", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    # Isolate the output path so we can assert what actually lands on disk.
    out_path = tmp_path / "out.json"
    monkeypatch.setattr(
        "src.services.connection.connection_orchestrator.OUTPUT_CONFIG_PATH",
        str(out_path),
    )
    # Capture loguru INFO output (the pin line is a loguru INFO record),
    # restoring all pre-existing handlers afterwards so other tests keep logs.
    pre_handlers = loguru.logger._core.handlers.copy()
    sink = io.StringIO()
    loguru.logger.remove()
    loguru.logger.add(sink, format="{message}", level="INFO")
    try:
        orch = _make_orchestrator()
        ok, _ = orch._attempt_single_connection(
            "standard",
            _server_config(),
            "vpn",
            use_singbox=True,
            file_path="C:/tmp/unused.json",
            step_callback=None,
        )
    finally:
        loguru.logger.remove()
        for hid, handler in pre_handlers.items():
            loguru.logger._core.handlers[hid] = handler

    assert ok == orch.ATTEMPT_SUCCESS, "TUN flow must succeed"
    # The pinned IP must have landed in the file Xray actually starts with.
    with open(out_path, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    dial = on_disk["outbounds"][0]["settings"]["vnext"][0]["address"]
    assert dial == "188.114.99.6", f"outbound not pinned on disk: {dial}"
    assert (
        on_disk["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"]
        == "4fcb3020-64c0-4e4d-b23b-xenups.ir"
    ), "SNI must stay untouched"
    # The wire log line must have been emitted (this is what the live run shows).
    assert "TUN mode: outbound '1mobility.zenups.ir' -> 188.114.99.6" in sink.getvalue(), (
        "pinning log line missing from the real flow"
    )


def test_proxy_flow_leaves_domain_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.connection.connection_orchestrator.OUTPUT_CONFIG_PATH",
        str(tmp_path / "out.json"),
    )
    orch = _make_orchestrator()
    ok, _ = orch._attempt_single_connection(
        "standard",
        _server_config(),
        "proxy",
        use_singbox=False,
        file_path="C:/tmp/unused.json",
        step_callback=None,
    )
    assert ok == orch.ATTEMPT_SUCCESS
    with open(tmp_path / "out.json", encoding="utf-8") as fh:
        on_disk = json.load(fh)
    dial = on_disk["outbounds"][0]["settings"]["vnext"][0]["address"]
    assert dial == "1mobility.zenups.ir", "proxy mode must keep the domain as-is"
