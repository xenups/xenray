"""Sing-box Service Manager (safe, clean, fully compatible with sing-box 1.12.12)."""

import ipaddress
import json
import os
import socket
import subprocess
import time
from typing import List, Optional, Union

from loguru import logger

from src.core.constants import (
    DNS_PROVIDERS,
    SINGBOX_CONFIG_PATH,
    SINGBOX_EXECUTABLE,
    SINGBOX_LOG_FILE,
    SINGBOX_PID_FILE,
    SINGBOX_RULE_SETS,
    TOR_EXECUTABLE,
    XRAY_EXECUTABLE,
)
from src.utils.network_interface import NetworkInterfaceDetector
from src.utils.platform_utils import PlatformUtils
from src.utils.process_utils import ProcessUtils

# Constants
XRAY_READY_RETRY_COUNT = 20
XRAY_READY_RETRY_DELAY = 0.5  # seconds
XRAY_READY_TIMEOUT = XRAY_READY_RETRY_COUNT * XRAY_READY_RETRY_DELAY  # 10 seconds
SINGBOX_START_DELAY = 2.0  # seconds
PROCESS_TERMINATE_TIMEOUT = 8.0  # seconds
DNS_RESOLUTION_TIMEOUT = 5.0  # seconds


class SingboxService:
    """Manages Sing-box TUN process with safe loop prevention."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._pid: Optional[int] = None
        self._log_handle = None
        self._added_routes: List[str] = []
        # Support PID adoption for CLI
        self._check_and_restore_pid()

    def _check_and_restore_pid(self):
        """Restore PID from file if it's still running."""
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[SingboxService] Restored PID {self._pid} from file")
            except Exception:
                pass

    def _normalize_list(self, value: Union[str, List[str], None]) -> List[str]:
        """Normalize input to list of strings."""
        if not value:
            return []
        if isinstance(value, str):
            value = [value]
        return [
            item.strip().lower().replace("'", "").replace('"', "").replace("[", "").replace("]", "")
            for item in value
            if isinstance(item, str)
        ]

    def _filter_real_ips(self, lst: List[str]) -> List[str]:
        """Filter list to only include valid IP addresses."""
        result = []
        for item in lst:
            try:
                ipaddress.ip_address(item)
                result.append(item)
            except (ValueError, ipaddress.AddressValueError):
                continue
        return result

    def _filter_domains(self, lst: List[str]) -> List[str]:
        """Filter list to only include domain names (not IPs)."""
        return [
            item
            for item in lst
            if not any(item.endswith(f".{x}") or item == x for x in self._filter_real_ips(lst + [item]))
        ]

    def _resolve_ips(self, endpoints: List[str]) -> List[str]:
        """Resolve domain names to IP addresses with timeout."""
        resolved_ips = []
        for ep in endpoints:
            # Check if already an IP
            try:
                ipaddress.ip_address(ep)
                resolved_ips.append(ep)
                continue
            except (ValueError, ipaddress.AddressValueError):
                pass  # It's a domain, need to resolve

            try:
                logger.info(f"[SingboxService] Resolving {ep} for route bypass...")
                # Set timeout for DNS resolution
                socket.setdefaulttimeout(DNS_RESOLUTION_TIMEOUT)
                addrs = socket.getaddrinfo(ep, None, socket.AF_INET)
                ips = list({info[4][0] for info in addrs})
                logger.info(f"[SingboxService] Resolved {ep} → {ips}")
                resolved_ips.extend(ips)
            except (socket.gaierror, socket.timeout, OSError) as e:
                logger.warning(f"[SingboxService] Failed to resolve {ep}: {e}")
            finally:
                socket.setdefaulttimeout(None)  # Reset timeout
        return list(set(resolved_ips))

    def _add_static_route(self, ip: str, gateway: str) -> None:
        """Add static route for IP via gateway."""
        if ip in self._added_routes:
            return
        try:
            logger.info(f"[SingboxService] Adding static route: {ip} → {gateway}")

            # Platform-specific route commands
            platform = PlatformUtils.get_platform()

            if platform == "windows":
                cmd = [
                    "route",
                    "add",
                    ip,
                    "mask",
                    "255.255.255.255",
                    gateway,
                    "metric",
                    "1",
                ]
            elif platform == "macos":
                cmd = [
                    "route",
                    "-n",
                    "add",
                    "-host",
                    ip,
                    gateway,
                ]
            else:  # Linux
                cmd = [
                    "ip",
                    "route",
                    "add",
                    ip,
                    "via",
                    gateway,
                ]

            subprocess.run(
                cmd,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            self._added_routes.append(ip)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[SingboxService] Failed to add route for {ip}: {e}")

    def _cleanup_routes(self) -> None:
        """Remove all added static routes."""
        platform = PlatformUtils.get_platform()

        for ip in self._added_routes[:]:
            try:
                logger.debug(f"[SingboxService] Removing static route: {ip}")

                # Platform-specific route delete commands
                if platform == "windows":
                    cmd = ["route", "delete", ip]
                elif platform == "macos":
                    cmd = ["route", "-n", "delete", "-host", ip]
                else:  # Linux
                    cmd = ["ip", "route", "del", ip]

                subprocess.run(
                    cmd,
                    check=False,
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )
            except (OSError, subprocess.SubprocessError) as e:
                logger.warning(f"[SingboxService] Failed to remove route for {ip}: {e}")
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
        mode: str = "vpn",
    ) -> Optional[int]:
        """Start Sing-box TUN service."""
        try:
            # 1. Detect interface & gateway
            (
                iface_name,
                iface_ip,
                _,
                gateway,
            ) = NetworkInterfaceDetector.get_primary_interface()
            if not gateway:
                logger.warning("[SingboxService] No gateway detected! Route bypass may be incomplete.")

            # 2. Bypass list: Proxy server + Common DNS servers
            bypass_list = self._normalize_list(proxy_server_ip)
            bypass_list.extend(DNS_PROVIDERS["bypass_list"])

            # Add User "Direct" IPs to bypass list so they get static routes
            if routing_rules and "direct" in routing_rules:
                direct_ips = self._filter_real_ips(routing_rules["direct"])
                # We should technically resolve direct domains too if we want static routes...
                # But resolving generic user domains might be slow/complex.
                # For now, only explicit IPs in direct list get static routes.
                bypass_list.extend(direct_ips)

            resolved_ips = self._resolve_ips(bypass_list)

            # 3. Add static routes for all resolved IPs
            if gateway:
                for ip in resolved_ips:
                    self._add_static_route(ip, gateway)

            # 4. Generate config - pass interface name for default_interface and MTU
            config = self._generate_config(
                xray_socks_port,
                proxy_server_ip,
                routing_country,
                iface_name,
                routing_rules,
                mtu,
                mode,
            )

            # 5. Wait for Xray to be ready (with retry)
            if mode != "tor":
                if not self._wait_for_xray_ready(xray_socks_port):
                    self._cleanup_routes()
                    return None

            # 6. Write config & start sing-box
            if not self._write_config_and_start(config):
                self._cleanup_routes()
                return None

            self._pid = self._process.pid

            # Write PID file
            try:
                with open(SINGBOX_PID_FILE, "w") as f:
                    f.write(str(self._pid))
            except Exception as e:
                logger.error(f"[SingboxService] Failed to write PID file: {e}")

            logger.info(f"[SingboxService] sing-box started successfully | PID: {self._pid}")
            return self._pid

        except Exception as e:
            logger.exception(f"[SingboxService] Failed to start: {e}")
            self._close_log()
            self._cleanup_routes()
            return None

    def _wait_for_xray_ready(self, port: int) -> bool:
        """Wait for Xray SOCKS port to be ready."""
        logger.info(f"[SingboxService] Waiting for Xray on port {port}...")
        for i in range(XRAY_READY_RETRY_COUNT):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    logger.info("[SingboxService] Xray is ready.")
                    return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                time.sleep(XRAY_READY_RETRY_DELAY)

        logger.error("[SingboxService] Timed out waiting for Xray.")
        return False

    def _write_config_and_start(self, config: dict) -> bool:
        """Write config to file and start process."""
        try:
            # Write config
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            # Open Log File
            self._log_handle = open(SINGBOX_LOG_FILE, "w", encoding="utf-8")

            # Start Process - use both creationflags and startupinfo for complete window hiding
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            startupinfo = PlatformUtils.get_startupinfo()
            self._process = subprocess.Popen(
                [SINGBOX_EXECUTABLE, "run", "-c", SINGBOX_CONFIG_PATH],
                stdout=self._log_handle,
                stderr=self._log_handle,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
            return True
        except Exception as e:
            logger.error(f"[SingboxService] Failed to start process: {e}")
            self._close_log()
            return False

    def _close_log(self):
        """Close log file handle."""
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def stop(self):
        """Stop the Sing-box service."""
        if self._process or self._pid:
            pid_to_kill = self._pid or (self._process.pid if self._process else None)
            if pid_to_kill:
                try:
                    ProcessUtils.kill_process(pid_to_kill, force=False)
                    # wait briefly
                    time.sleep(0.5)
                    if ProcessUtils.is_running(pid_to_kill):
                        ProcessUtils.kill_process(pid_to_kill, force=True)
                except Exception as e:
                    logger.error(f"[SingboxService] Error stopping process: {e}")

            self._process = None
            self._pid = None

        # Remove PID file
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                os.remove(SINGBOX_PID_FILE)
            except Exception:
                pass

        self._cleanup_routes()
        self._close_log()
        logger.info("[SingboxService] Stopped.")

    def is_running(self) -> bool:
        """Check if sing-box is running."""
        if self._pid and ProcessUtils.is_running(self._pid):
            return True

        # Fallback to PID file
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    return True
            except Exception:
                pass

        # Clear stale state
        self._pid = None
        self._process = None
        return False

    @property
    def pid(self) -> Optional[int]:
        """Get sing-box process ID."""
        return self._pid

    def get_version(self) -> Optional[str]:
        """Get installed Sing-box version."""
        if not os.path.exists(SINGBOX_EXECUTABLE):
            return None
        try:
            # Output: "sing-box version 1.8.0 ..."
            result = subprocess.run(
                [SINGBOX_EXECUTABLE, "version"],
                capture_output=True,
                text=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            if result.returncode == 0:
                first_line = result.stdout.split("\n")[0]
                parts = first_line.split()
                if len(parts) >= 3:
                    return parts[2]  # "1.8.0"
            return None
        except Exception:
            return None

    # ────────────────────────────────────────────────────────────────
    # CONFIG GENERATOR — 100% WORKING & LOOP-PROOF
    # ────────────────────────────────────────────────────────────────
    def _generate_config(
        self,
        socks_port: int,
        proxy_server_ip: Union[str, List[str]],
        routing_country: str = "",
        interface_name: Optional[str] = None,
        routing_rules: dict = None,
        mtu: int = 1420,
        mode: str = "vpn",
    ) -> dict:
        """Generate Sing-box configuration."""
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
                        "type": "tcp" if mode == "tor" else "udp",
                        "server": "1.1.1.1",
                        "detour": "proxy",
                    },
                ],
                "rules": [
                    {
                        "inbound": ["tun-in"],
                        "server": "remote_proxy",
                    },
                    {"query_type": ["A", "AAAA"], "server": "remote_proxy"},
                ],
                "final": "remote_proxy",
                "strategy": "prefer_ipv4",
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": PlatformUtils.get_tun_interface_name(),
                    "address": ["172.20.0.1/30"],
                    "mtu": mtu,
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "system",
                    "sniff": True,
                    "sniff_override_destination": True,
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
                }
                if mode != "tor"
                else {
                    "type": "socks",
                    "tag": "proxy",
                    "server": "127.0.0.1",
                    "server_port": 9050,  # External Tor SOCKS port
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
                            "v2ray.exe",
                            "tor.exe",
                            "sing-box.exe",
                            "python.exe",
                            "obfs4proxy.exe",
                            "snowflake-client.exe",
                        ],
                        "outbound": "direct",
                    },
                    {"process_path": [XRAY_EXECUTABLE, TOR_EXECUTABLE], "outbound": "direct"},
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

        # 2. Add Proxy Server IP/Domain Bypass Rules
        insert_index = len([r for r in rules if "process" in r])

        for ip in proxy_ips + ["1.1.1.1", "8.8.8.8"]:
            rules.insert(insert_index, {"ip_cidr": f"{ip}/32", "outbound": "direct"})
            insert_index += 1

        for domain in proxy_domains:
            rules.insert(insert_index, {"domain_suffix": domain, "outbound": "direct"})
            insert_index += 1
            dns_rules.append({"domain_suffix": domain, "server": "bootstrap"})

        # --- USER ROUTING RULES (Direct / Proxy / Block) ---
        if routing_rules:
            # Helper: Validate IP/CIDR
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

                    # 1. Handle IP/CIDR
                    if is_valid_ip_cidr(t):
                        s_ips.append(t)
                        continue

                    # 2. Handle Tags
                    lower_t = t.lower()
                    if lower_t.startswith("geosite:") or lower_t.startswith("geoip:"):
                        # Incompatible with Singbox loose config (needs .db or rule_set)
                        # We skip to prevent crash, but maybe log it?
                        # logger.debug(f"Skipping Xray tag for Singbox: {t}")
                        continue

                    if lower_t.startswith("domain:"):
                        s_domain_suffixes.append(
                            t[7:]
                        )  # treat 'domain:' as suffix in xray usually means substring/suffix
                    elif lower_t.startswith("full:"):
                        s_domains.append(t[5:])  # exact match
                    else:
                        # Default assumption: It's a domain suffix (e.g. "google.com")
                        s_domain_suffixes.append(t)

                # Add Rules
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

        # 3. Country routing
        if routing_country and routing_country.lower() != "none":
            rule_sets_mapping = SINGBOX_RULE_SETS
            country = routing_country.lower()
            if country in rule_sets_mapping:
                if "rule_set" not in cfg["route"]:
                    cfg["route"]["rule_set"] = []

                for idx, url in enumerate(rule_sets_mapping[country]):
                    tag_name = f"{country}-rules-{idx}"

                    cfg["route"]["rule_set"].append(
                        {
                            "tag": tag_name,
                            "type": "remote",
                            "format": "binary",
                            "url": url,
                            "download_detour": "direct",
                            "update_interval": "24h",
                        }
                    )
                    rules.append({"rule_set": tag_name, "outbound": "direct"})
                    dns_rules.append({"rule_set": tag_name, "server": "bootstrap"})

        return cfg
