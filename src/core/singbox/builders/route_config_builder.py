"""Sing-box Inbounds, Outbounds, and Route base configuration builder."""

from __future__ import annotations

import os
import sys
from typing import List, Optional, Union

from src.core.constants import (
    BASE_BYPASS_PROCESSES,
    TUN_GATEWAY_IPV4,
    XRAY_EXECUTABLE,
)
from src.core.logger import logger
from src.utils.network_utils import NetworkUtils
from src.utils.platform_utils import PlatformUtils


class RouteConfigBuilder:
    """Constructs inbounds, outbounds, and base route blocks for sing-box."""

    def build_inbounds(self, mtu: int = 1420) -> list[dict]:
        """Build the TUN inbound block."""
        return [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": PlatformUtils.get_tun_interface_name(),
                # IPv4-only subnet — single address avoids IPv6 prefix binding
                # errors ("need one more IPv6 address...").
                "address": [TUN_GATEWAY_IPV4],
                "mtu": mtu,
                "auto_route": True,
                "strict_route": True,
                "stack": "mixed",
                "endpoint_independent_nat": True,
            }
        ]

    def build_outbounds(self, socks_port: int, interface_name: Optional[str] = None) -> list[dict]:
        """Build proxy, direct, and block outbounds.

        Outbound 'direct' remains purely interface-agnostic without static
        bind_interface, letting 'route.auto_detect_interface: true' handle
        dynamic interface switching seamlessly across Wi-Fi and Ethernet.
        """
        return [
            {
                "type": "socks",
                "tag": "proxy",
                "server": "127.0.0.1",
                "server_port": socks_port,
            },
            {
                "type": "direct",
                "tag": "direct",
            },
            {
                "type": "block",
                "tag": "block",
            },
        ]

    def build_base_route(
        self,
        interface_name: Optional[str] = None,
        bypass_process_names: Optional[List[str]] = None,
    ) -> dict:
        """Build the base route configuration block with default process and IP rules."""
        if bypass_process_names is not None:
            process_names = list(bypass_process_names)
        else:
            current_exe = os.path.basename(sys.executable).lower()
            is_win = sys.platform.startswith("win")
            process_names = [f"{proc}.exe" if is_win else proc for proc in BASE_BYPASS_PROCESSES]
            if current_exe not in process_names:
                process_names.append(current_exe)

        return {
            "rules": [
                # Process bypass FIRST — Python/curl/xray subprocess traffic
                # bypasses TUN on Windows before any IP/domain rules fire.
                {
                    "process_name": process_names,
                    "outbound": "direct",
                },
                {"process_path": [XRAY_EXECUTABLE], "outbound": "direct"},
                # Port-53 sniff so the DNS protocol can be detected for hijack.
                # Scoped to port 53 only to minimise per-packet overhead.
                {
                    "inbound": ["tun-in"],
                    "port": [53],
                    "action": "sniff",
                },
                {
                    "protocol": "dns",
                    "action": "hijack-dns",
                },
                {"network": "udp", "port": 443, "outbound": "proxy"},
                {"ip_cidr": ["224.0.0.0/3", "ff00::/8"], "outbound": "block"},
                {
                    "ip_cidr": [
                        "10.0.0.0/8",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "127.0.0.0/8",
                        "169.254.0.0/16",
                        "fc00::/7",  # IPv6 ULA
                        "fe80::/10",  # IPv6 Link-Local
                        "::1/128",  # IPv6 loopback
                    ],
                    "outbound": "direct",
                },
            ],
            "final": "proxy",
            "auto_detect_interface": True,
            # sing-box 1.12+ requires default_domain_resolver (the legacy
            # per-outbound `domain_resolver` field is deprecated and will be
            # removed in 1.14). bootstrap resolves domains for outbounds
            # that don't specify their own.
            "default_domain_resolver": "bootstrap",
            **({"default_interface": interface_name} if interface_name else {}),
        }

    def inject_loop_breakers(
        self,
        rules: list,
        dns_rules: list,
        proxy_ips: List[str],
        proxy_domains: List[str],
        sni_connect_ip: Optional[str] = None,
    ) -> int:
        """Inject proxy server bypass rules and SNI connect IP rules.

        PRIMARY strategy: Remote server IP:Port bypass (ip_cidr) placed at index 0
        of routing rules.
        FALLBACK strategy: Process-name rules (xray.exe) follow, ensuring anti-loop
        safety even if binary names vary or IPs are dynamically resolved.

        Returns:
            The insertion index for subsequent user rules.
        """
        # Primary strategy: insert at the very beginning (index 0) of the routing table
        insert_index = 0

        for ip in proxy_ips:
            rules.insert(insert_index, {"ip_cidr": f"{ip}/32", "outbound": "direct"})
            insert_index += 1

        for domain in proxy_domains:
            rules.insert(insert_index, {"domain_suffix": domain, "outbound": "direct"})
            insert_index += 1
            dns_rules.append({"domain_suffix": domain, "server": "bootstrap"})

        # SNI Spoof: CONNECT_IP loop-breaker
        connect_ip = sni_connect_ip
        if not connect_ip:
            try:
                from src.core.constants import CONFIG_DIR
                from src.repositories.settings_repository import SettingsRepository

                _settings = SettingsRepository(CONFIG_DIR)
                if _settings.get_sni_spoof_enabled():
                    connect_ip = _settings.get_sni_connect_ip()
            except Exception:
                connect_ip = None

        if connect_ip:
            rule = {"outbound": "direct"}
            if NetworkUtils.is_ipv4(connect_ip):
                rule["ip_cidr"] = connect_ip
            else:
                rule["domain"] = [connect_ip]
            rules.insert(insert_index, rule)
            insert_index += 1
            logger.debug(f"[RouteConfigBuilder] SNI spoof target direct rule: {connect_ip}")

        # Subsequent user rules should be inserted after loop-breakers and process fallback rules
        process_rule_count = len([r for r in rules if "process_name" in r or "process_path" in r])
        return insert_index + process_rule_count
