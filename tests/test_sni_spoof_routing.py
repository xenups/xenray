"""SNI-Spoof routing injection tests — sing-box + xray_config_processor."""

from unittest.mock import Mock

import pytest

from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder
from src.services.xray_config_processor import XrayConfigProcessor


@pytest.fixture
def fake_settings_repo(monkeypatch):
    """Patch SettingsRepository with controllable SNI flags."""

    class FakeRepo:
        def __init__(self, enabled, connect_ip):
            self.enabled = enabled
            self.connect_ip = connect_ip
            self.listen_port = 40443
            self.connect_port = 443

        def get_sni_spoof_enabled(self):
            return self.enabled

        def get_sni_connect_ip(self):
            return self.connect_ip

        def get_sni_listen_port(self):
            return self.listen_port

        def get_sni_connect_port(self):
            return self.connect_port

    import src.repositories.settings_repository as repo_mod

    instances = {}

    def _fake_factory(enabled, connect_ip="185.193.30.94"):
        fake = FakeRepo(enabled, connect_ip)
        instances["singbox"] = fake
        # singbox_config_builder does `from ...settings_repository import SettingsRepository`
        # inside the method, so patch the real module's name.
        monkeypatch.setattr(repo_mod, "SettingsRepository", lambda *a, **k: fake)
        return fake

    return _fake_factory


def _build_singbox():
    builder = SingboxConfigBuilder()
    return builder.build(
        socks_port=10805,
        proxy_server_ip="",
        routing_country="",
        interface_name=None,
        routing_rules={"direct": [], "proxy": [], "block": []},
        mtu=1420,
    )


class TestSingboxSniRouting:
    def test_disabled_no_sni_rule(self, fake_settings_repo):
        fake_settings_repo(False)
        cfg = _build_singbox()
        rules = cfg["route"]["rules"]
        assert not any(r.get("ip_cidr") == "185.193.30.94" for r in rules)

    def test_enabled_connect_ip_goes_direct(self, fake_settings_repo):
        fake_settings_repo(True)
        cfg = _build_singbox()
        rules = cfg["route"]["rules"]
        sni = [r for r in rules if r.get("ip_cidr") == "185.193.30.94"]
        assert sni, "CONNECT_IP direct rule missing when SNI enabled"
        assert sni[0]["outbound"] == "direct"

    def test_enabled_domain_connect_ip_goes_direct_via_domain(self, fake_settings_repo):
        fake_settings_repo(True, connect_ip="chess.com")
        cfg = _build_singbox()
        rules = cfg["route"]["rules"]
        sni = [r for r in rules if r.get("domain") == ["chess.com"]]
        assert sni, "domain CONNECT_IP direct rule missing"
        assert sni[0]["outbound"] == "direct"


class TestXraySniRouting:
    def _processor(self, sni_enabled=False):
        ctx = Mock()
        ctx.settings = Mock()
        ctx.settings.get_sni_spoof_enabled.return_value = sni_enabled
        ctx.settings.get_sni_connect_ip.return_value = "185.193.30.94"
        ctx.settings.get_sni_listen_port.return_value = 40443
        ctx.routing = Mock()
        ctx.routing.load_rules.return_value = {"direct": [], "proxy": [], "block": []}
        proc = XrayConfigProcessor(ctx)
        # Neutralize the DNS configurator (not under test here) so a plain
        # config dict passes through without a Mock-iteration crash.
        proc._dns_configurator = Mock()
        proc._dns_configurator.configure = lambda *a, **k: None
        proc._config_patcher = Mock()
        proc._config_patcher.safe_patch = lambda *a, **k: None
        return proc

    def test_disabled_no_sni_outbound(self):
        proc = self._processor(False)
        cfg = proc.process_config(
            {"inbounds": [], "outbounds": [], "routing": {"rules": []}}, mode="proxy"
        )
        tags = [o.get("tag") for o in cfg["outbounds"]]
        assert "sni-spoof" not in tags

    def test_enabled_redirects_dial_address_without_overriding_disk_connect_ip(self):
        proc = self._processor(True)
        base = {
            "inbounds": [],
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {
                        "vnext": [{"address": "oracle.example.com", "port": 443}]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "tlsSettings": {"serverName": "oracle.example.com"},
                    },
                }
            ],
            "routing": {"rules": []},
        }
        cfg = proc.process_config(base, mode="proxy")
        out = cfg["outbounds"][0]
        # The DIAL address is pointed at the local relay...
        assert out["settings"]["vnext"][0]["address"] == "127.0.0.1"
        assert out["settings"]["vnext"][0]["port"] == 40443
        # ...but the user-configured CONNECT_IP on disk is NEVER touched...
        proc._app_context.settings.set_sni_connect_ip.assert_not_called()
        proc._app_context.settings.set_sni_connect_port.assert_not_called()
        # ...and the real server's SNI/serverName stays in the outbound header.
        assert (
            out["streamSettings"]["tlsSettings"]["serverName"] == "oracle.example.com"
        )

    def test_enabled_without_proxy_outbound_adds_nothing(self):
        proc = self._processor(True)
        cfg = proc.process_config(
            {"inbounds": [], "outbounds": [], "routing": {"rules": []}}, mode="proxy"
        )
        assert cfg["outbounds"] == []
