"""Sing-box TUN Service — manages the sing-box TUN process for VPN mode."""

import ipaddress
import json
import os
import socket
import subprocess
import time
from typing import List, Optional, Union

from loguru import logger

from src.core.constants import (
    SINGBOX_CONFIG_PATH,
    SINGBOX_EXECUTABLE,
    SINGBOX_LOG_FILE,
    SINGBOX_PID_FILE,
    SINGBOX_RULE_SETS,
)
from src.utils.network_interface import NetworkInterfaceDetector
from src.utils.platform_utils import PlatformUtils
from src.utils.process_utils import ProcessUtils

XRAY_READY_RETRY_COUNT = 20
XRAY_READY_RETRY_DELAY = 0.5
DNS_RESOLUTION_TIMEOUT = 5.0


class SingboxTunService:
    """Manages the sing-box TUN process for VPN mode."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._pid: Optional[int] = None
        self._log_handle = None
        self._added_routes: List[str] = []

    def _normalize_list(self, value: Union[str, List[str], None]) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            value = [value]
        return [item.strip().lower().replace("'", "").replace('"', "") for item in value if isinstance(item, str)]

    def _filter_real_ips(self, lst: List[str]) -> List[str]:
        result = []
        for item in lst:
            try:
                ipaddress.ip_address(item)
                result.append(item)
            except (ValueError, ipaddress.AddressValueError):
                continue
        return result

    def _filter_domains(self, lst: List[str]) -> List[str]:
        return [
            item
            for item in lst
            if not any(item.endswith(f".{x}") or item == x for x in self._filter_real_ips(lst + [item]))
        ]

    def _resolve_ips(self, endpoints: List[str]) -> List[str]:
        resolved_ips = []
        old_timeout = socket.getdefaulttimeout()
        for ep in endpoints:
            try:
                ipaddress.ip_address(ep)
                resolved_ips.append(ep)
                continue
            except (ValueError, ipaddress.AddressValueError):
                pass
            try:
                logger.info(f"[SingboxTunService] Resolving {ep} for route bypass...")
                socket.setdefaulttimeout(DNS_RESOLUTION_TIMEOUT)
                addrs = socket.getaddrinfo(ep, None, socket.AF_INET)
                ips = list({info[4][0] for info in addrs})
                logger.info(f"[SingboxTunService] Resolved {ep} -> {ips}")
                resolved_ips.extend(ips)
            except (socket.gaierror, socket.timeout, OSError) as e:
                logger.warning(f"[SingboxTunService] Failed to resolve {ep}: {e}")
            finally:
                socket.setdefaulttimeout(old_timeout)
        return list(set(resolved_ips))

    def _add_static_route(self, ip: str, gateway: str) -> None:
        if ip in self._added_routes:
            return
        try:
            logger.info(f"[SingboxTunService] Adding static route: {ip} -> {gateway}")
            platform = PlatformUtils.get_platform()
            if platform == "windows":
                cmd = ["route", "add", ip, "mask", "255.255.255.255", gateway, "metric", "1"]
            elif platform == "macos":
                cmd = ["route", "-n", "add", "-host", ip, gateway]
            else:
                cmd = ["ip", "route", "add", ip, "via", gateway]
            subprocess.run(
                cmd,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            self._added_routes.append(ip)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[SingboxTunService] Failed to add route for {ip}: {e}")

    def _cleanup_routes(self) -> None:
        platform = PlatformUtils.get_platform()
        for ip in self._added_routes[:]:
            try:
                logger.debug(f"[SingboxTunService] Removing static route: {ip}")
                if platform == "windows":
                    cmd = ["route", "delete", ip]
                elif platform == "macos":
                    cmd = ["route", "-n", "delete", "-host", ip]
                else:
                    cmd = ["ip", "route", "del", ip]
                subprocess.run(
                    cmd,
                    check=False,
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )
            except (OSError, subprocess.SubprocessError) as e:
                logger.warning(f"[SingboxTunService] Failed to remove route for {ip}: {e}")
            finally:
                if ip in self._added_routes:
                    self._added_routes.remove(ip)

    def start(
        self,
        xray_socks_port: int,
        proxy_server_ip: Union[str, List[str]] = "",
        routing_country: str = "",
        routing_rules: dict = None,
        mtu: int = 1420,
    ) -> Optional[int]:
        """Start sing-box TUN service pointing to Xray SOCKS proxy."""
        try:
            iface_name, iface_ip, _, gateway = NetworkInterfaceDetector.get_primary_interface()
            if not gateway:
                logger.warning("[SingboxTunService] No gateway detected!")

            bypass_list = self._normalize_list(proxy_server_ip)
            bypass_list.extend(["1.1.1.1", "8.8.8.8", "dns.google", "cloudflare-dns.com"])

            if routing_rules and "direct" in routing_rules:
                direct_ips = self._filter_real_ips(routing_rules["direct"])
                bypass_list.extend(direct_ips)

            resolved_ips = self._resolve_ips(bypass_list)
            if gateway:
                for ip in resolved_ips:
                    self._add_static_route(ip, gateway)

            config = self._generate_config(
                socks_port=xray_socks_port,
                proxy_server_ip=proxy_server_ip,
                routing_country=routing_country,
                interface_name=iface_name,
                routing_rules=routing_rules,
                mtu=mtu,
            )

            if not self._wait_for_xray_ready(xray_socks_port):
                self._cleanup_routes()
                return None

            if not self._write_config_and_start(config):
                self._cleanup_routes()
                return None

            self._pid = self._process.pid
            try:
                with open(SINGBOX_PID_FILE, "w") as f:
                    f.write(str(self._pid))
            except Exception as e:
                logger.error(f"[SingboxTunService] Failed to write PID file: {e}")

            logger.info(f"[SingboxTunService] sing-box started | PID: {self._pid}")
            return self._pid

        except Exception as e:
            logger.exception(f"[SingboxTunService] Failed to start: {e}")
            self._close_log()
            self._cleanup_routes()
            return None

    def _wait_for_xray_ready(self, port: int) -> bool:
        logger.info(f"[SingboxTunService] Waiting for Xray on port {port}...")
        for i in range(XRAY_READY_RETRY_COUNT):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    logger.info("[SingboxTunService] Xray is ready.")
                    return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                time.sleep(XRAY_READY_RETRY_DELAY)
        logger.error("[SingboxTunService] Timed out waiting for Xray.")
        return False

    def _write_config_and_start(self, config: dict) -> bool:
        try:
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            self._log_handle = open(SINGBOX_LOG_FILE, "w", encoding="utf-8")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(
                [SINGBOX_EXECUTABLE, "run", "-c", SINGBOX_CONFIG_PATH],
                stdout=self._log_handle,
                stderr=self._log_handle,
                creationflags=flags,
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            return True
        except Exception as e:
            logger.error(f"[SingboxTunService] Failed to start process: {e}")
            self._close_log()
            return False

    def _close_log(self):
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def stop(self):
        """Stop the sing-box TUN service."""
        if self._process or self._pid:
            pid_to_kill = self._pid or (self._process.pid if self._process else None)
            if pid_to_kill:
                try:
                    ProcessUtils.kill_process(pid_to_kill, force=False)
                    time.sleep(0.5)
                    if ProcessUtils.is_running(pid_to_kill):
                        ProcessUtils.kill_process(pid_to_kill, force=True)
                except Exception as e:
                    logger.error(f"[SingboxTunService] Error stopping process: {e}")
            self._process = None
            self._pid = None

        if os.path.exists(SINGBOX_PID_FILE):
            try:
                os.remove(SINGBOX_PID_FILE)
            except Exception:
                pass

        self._cleanup_routes()
        self._close_log()
        logger.info("[SingboxTunService] Stopped.")

    def is_running(self) -> bool:
        if self._pid and ProcessUtils.is_running(self._pid):
            return True
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    return True
            except Exception:
                pass
        self._pid = None
        self._process = None
        return False

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    def _generate_config(
        self,
        socks_port: int,
        proxy_server_ip: Union[str, List[str]],
        routing_country: str = "",
        interface_name: Optional[str] = None,
        routing_rules: dict = None,
        mtu: int = 1420,
    ) -> dict:
        """Generate sing-box TUN configuration."""
        proxy_list = self._normalize_list(proxy_server_ip)
        proxy_ips = self._filter_real_ips(proxy_list)
        proxy_domains = self._filter_domains(proxy_list)

        cfg = {
            "log": {"level": "info", "timestamp": True},
            "experimental": {
                "clash_api": {
                    "external_controller": "127.0.0.1:9090",
                    "secret": "",
                }
            },
            "dns": {
                "servers": [
                    {
                        "tag": "bootstrap",
                        "type": "udp",
                        "server": "8.8.8.8",
                        "detour": "direct",
                    },
                    {
                        "tag": "remote_proxy",
                        "type": "https",
                        "server": "1.1.1.1",
                        "domain_resolver": "bootstrap",
                        "detour": "proxy",
                    },
                ],
                "rules": [
                    {"inbound": ["tun-in"], "server": "remote_proxy"},
                    {"query_type": ["A", "AAAA"], "server": "remote_proxy"},
                ],
                "final": "remote_proxy",
                "strategy": "prefer_ipv4",
                "disable_cache": False,
                "disable_expire": False,
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": PlatformUtils.get_tun_interface_name(),
                    "address": ["172.20.0.1/30", "fd00::1/126"],
                    "mtu": mtu,
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "mixed",
                    "endpoint_independent_nat": True,
                }
            ],
            "outbounds": [
                {
                    "type": "socks",
                    "tag": "proxy",
                    "server": "127.0.0.1",
                    "server_port": socks_port,
                    "domain_resolver": "remote_proxy",
                },
                {
                    "type": "direct",
                    "tag": "direct",
                    "domain_resolver": "bootstrap",
                    **({"bind_interface": interface_name} if interface_name else {}),
                },
                {"type": "block", "tag": "block"},
            ],
            "route": {
                "rules": [
                    {
                        "process_name": [
                            "xray.exe",
                            "xray",
                            "v2ray.exe",
                            "v2ray",
                            "sing-box.exe",
                            "sing-box",
                            "xenray.exe",
                            "xenray",
                            "python.exe",
                            "python",
                            "python3",
                            "curl.exe",
                            "curl",
                        ],
                        "outbound": "direct",
                    },
                    {"process_path": [os.path.abspath(SINGBOX_EXECUTABLE)], "outbound": "direct"},
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
                            "fc00::/7",
                            "fe80::/10",
                            "::1/128",
                        ],
                        "outbound": "direct",
                    },
                ],
                "final": "proxy",
                "auto_detect_interface": True,
                **({"default_interface": interface_name} if interface_name else {}),
            },
        }

        rules = cfg["route"]["rules"]
        dns_rules = cfg["dns"]["rules"]

        insert_index = len([r for r in rules if "process" in r])

        for ip in proxy_ips + ["1.1.1.1", "8.8.8.8"]:
            rules.insert(insert_index, {"ip_cidr": f"{ip}/32", "outbound": "direct"})
            insert_index += 1

        for domain in proxy_domains:
            rules.insert(insert_index, {"domain_suffix": domain, "outbound": "direct"})
            insert_index += 1
            dns_rules.append({"domain_suffix": domain, "server": "bootstrap"})

        if routing_rules:

            def is_valid_ip_cidr(val):
                try:
                    ipaddress.ip_network(val, strict=False)
                    return True
                except ValueError:
                    return False

            for action in ["direct", "proxy", "block"]:
                if action not in routing_rules:
                    continue
                targets = routing_rules[action]
                outbound_tag = action
                s_ips = []
                s_domains = []
                s_domain_suffixes = []

                for t in targets:
                    t = t.strip()
                    if not t:
                        continue
                    if is_valid_ip_cidr(t):
                        s_ips.append(t)
                        continue
                    lower_t = t.lower()
                    if lower_t.startswith("geosite:") or lower_t.startswith("geoip:"):
                        continue
                    if lower_t.startswith("domain:"):
                        s_domain_suffixes.append(t[7:])
                    elif lower_t.startswith("full:"):
                        s_domains.append(t[5:])
                    else:
                        s_domain_suffixes.append(t)

                if s_ips:
                    rules.append({"ip_cidr": s_ips, "outbound": outbound_tag})
                if s_domains:
                    rules.append({"domain": s_domains, "outbound": outbound_tag})
                    if outbound_tag == "direct":
                        dns_rules.append({"domain": s_domains, "server": "bootstrap"})
                if s_domain_suffixes:
                    rules.append({"domain_suffix": s_domain_suffixes, "outbound": outbound_tag})
                    if outbound_tag == "direct":
                        dns_rules.append({"domain_suffix": s_domain_suffixes, "server": "bootstrap"})

        if routing_country and routing_country.lower() != "none":
            country = routing_country.lower()
            logger.info(f"[SingboxTunService] Applying country-based routing for: {country}")
            if country in SINGBOX_RULE_SETS:
                if "rule_set" not in cfg["route"]:
                    cfg["route"]["rule_set"] = []
                for idx, url in enumerate(SINGBOX_RULE_SETS[country]):
                    tag_name = f"{country}-rules-{idx}"
                    fmt = "source" if url.endswith(".json") else "binary"
                    cfg["route"]["rule_set"].append({
                        "tag": tag_name,
                        "type": "remote",
                        "format": fmt,
                        "url": url,
                        "download_detour": "direct",
                        "update_interval": "24h",
                    })
                    rules.append({"rule_set": tag_name, "outbound": "direct"})
                    dns_rules.append({"rule_set": tag_name, "server": "bootstrap"})

        return cfg
