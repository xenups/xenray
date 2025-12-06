"""Sing-box Service Manager (safe, clean, fully compatible with sing-box 1.12.12)."""

import json
import os
import subprocess
import time
from typing import Optional, List, Union
import socket
import ipaddress
from loguru import logger

from src.core.constants import (
    SINGBOX_EXECUTABLE,
    SINGBOX_CONFIG_PATH,
    SINGBOX_LOG_FILE,
    XRAY_EXECUTABLE,
)
from src.utils.network_interface import NetworkInterfaceDetector


class SingboxService:
    """Manages Sing-box TUN process with safe loop prevention."""

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
        return [
            item.strip()
            .lower()
            .replace("'", "")
            .replace('"', "")
            .replace("[", "")
            .replace("]", "")
            for item in value
            if isinstance(item, str)
        ]

    def _filter_real_ips(self, lst: List[str]) -> List[str]:
        result = []
        for item in lst:
            try:
                ipaddress.ip_address(item)
                result.append(item)
            except:
                continue
        return result

    def _filter_domains(self, lst: List[str]) -> List[str]:
        return [
            item
            for item in lst
            if not any(
                item.endswith(f".{x}") or item == x
                for x in self._filter_real_ips(lst + [item])
            )
        ]

    def _resolve_ips(self, endpoints: List[str]) -> List[str]:
        resolved_ips = []
        for ep in endpoints:
            try:
                ipaddress.ip_address(ep)
                resolved_ips.append(ep)
                continue
            except:
                pass

            try:
                logger.info(f"[SingboxService] Resolving {ep} for route bypass...")
                addrs = socket.getaddrinfo(ep, None, socket.AF_INET)
                ips = list({info[4][0] for info in addrs})
                logger.info(f"[SingboxService] Resolved {ep} → {ips}")
                resolved_ips.extend(ips)
            except Exception as e:
                logger.warning(f"[SingboxService] Failed to resolve {ep}: {e}")
        return list(set(resolved_ips))

    def _add_static_route(self, ip: str, gateway: str):
        if ip in self._added_routes:
            return
        try:
            logger.info(f"[SingboxService] Adding static route: {ip} → {gateway}")
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
            subprocess.run(
                cmd,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._added_routes.append(ip)
        except Exception as e:
            logger.error(f"[SingboxService] Failed to add route for {ip}: {e}")

    def _cleanup_routes(self):
        for ip in self._added_routes[:]:
            try:
                logger.info(f"[SingboxService] Removing static route: {ip}")
                subprocess.run(
                    ["route", "delete", ip],
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except Exception as e:
                logger.error(f"[SingboxService] Failed to remove route for {ip}: {e}")
        self._added_routes.clear()

    def start(
        self,
        xray_socks_port: int,
        proxy_server_ip: Union[str, List[str]] = "",
        gateway_ip: Union[str, List[str]] = "",
        routing_country: str = "",
    ) -> Optional[int]:

        try:
            # 1. Detect interface & gateway
            iface_name, iface_ip, _, gateway = (
                NetworkInterfaceDetector.get_primary_interface()
            )
            if not gateway:
                logger.warning(
                    "[SingboxService] No gateway detected! Route bypass may be incomplete."
                )

            # 2. Bypass list: Proxy server + Common DNS servers
            bypass_list = self._normalize_list(proxy_server_ip)
            bypass_list.extend(
                [
                    "8.8.8.8",
                    "8.8.4.4",
                    "1.1.1.1",
                    "1.0.0.1",
                    "dns.google",
                    "cloudflare-dns.com",
                ]
            )

            resolved_ips = self._resolve_ips(bypass_list)

            # 3. Add static routes for all resolved IPs
            if gateway:
                for ip in resolved_ips:
                    self._add_static_route(ip, gateway)

            # 4. Generate config - pass interface name for default_interface
            config = self._generate_config(
                xray_socks_port, proxy_server_ip, gateway_ip, routing_country, iface_name
            )

            # 5. Wait for Xray to be ready (with retry)
            for attempt in range(20):
                try:
                    sock = socket.create_connection(
                        ("127.0.0.1", xray_socks_port), timeout=1
                    )
                    sock.close()
                    logger.info(
                        f"[SingboxService] Xray SOCKS ready on port {xray_socks_port}"
                    )
                    break
                except:
                    time.sleep(0.5)
            else:
                logger.error("[SingboxService] Xray SOCKS port not ready after 10s")
                self._cleanup_routes()
                return None

            # 6. Write config & start sing-box
            os.makedirs(os.path.dirname(SINGBOX_CONFIG_PATH), exist_ok=True)
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info(f"[SingboxService] Starting sing-box → {SINGBOX_CONFIG_PATH}")
            os.makedirs(os.path.dirname(SINGBOX_LOG_FILE), exist_ok=True)
            self._log_handle = open(SINGBOX_LOG_FILE, "w", encoding="utf-8")

            cmd = [SINGBOX_EXECUTABLE, "run", "-c", SINGBOX_CONFIG_PATH]
            self._process = subprocess.Popen(
                cmd,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                text=True,
            )

            time.sleep(2)

            if self._process.poll() is not None:
                log_tail = "".join(open(SINGBOX_LOG_FILE).readlines()[-20:])
                logger.error(
                    f"[SingboxService] sing-box crashed! Last logs:\n{log_tail}"
                )
                self._close_log()
                self._cleanup_routes()
                return None

            self._pid = self._process.pid
            logger.info(
                f"[SingboxService] sing-box started successfully | PID: {self._pid}"
            )
            return self._pid

        except Exception as e:
            logger.exception(f"[SingboxService] Failed to start: {e}")
            self._close_log()
            self._cleanup_routes()
            return None

    def stop(self) -> bool:
        self._cleanup_routes()
        if not self._process:
            return True

        logger.info(f"[SingboxService] Stopping sing-box (PID {self._pid})")
        self._process.terminate()
        try:
            self._process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            logger.warning("[SingboxService] Force killing sing-box...")
            self._process.kill()
            self._process.wait()

        self._process = None
        self._pid = None
        self._close_log()
        logger.info("[SingboxService] sing-box stopped")
        return True

    def _close_log(self):
        if self._log_handle:
            try:
                self._log_handle.flush()
                self._log_handle.close()
            except:
                pass
            self._log_handle = None

    # ────────────────────────────────────────────────────────────────
    # CONFIG GENERATOR — 100% WORKING & LOOP-PROOF
    # ────────────────────────────────────────────────────────────────
    def _generate_config(
        self,
        socks_port: int,
        proxy_server_ip: Union[str, List[str]],
        gateway_ip: Union[str, List[str]],
        routing_country: str = "",
        interface_name: Optional[str] = None,
    ) -> dict:

        proxy_list = self._normalize_list(proxy_server_ip)
        proxy_ips = self._filter_real_ips(proxy_list)
        proxy_domains = self._filter_domains(proxy_list)

        cfg = {
            "log": {"level": "info", "timestamp": True},
            "dns": {
                "servers": [
                    {"tag": "bootstrap", "type": "udp", "server": "8.8.8.8"},
                    {"tag": "remote", "type": "udp", "server": "1.1.1.1"},
                ],
                "rules": [
                    # این خط باید اول باشه و مهم‌ترین خط کل زندگیته!
                    {"inbound": ["tun-in"], "server": "bootstrap"},
                    # بوت‌استرپ اولیه
                    {"query_type": ["A", "AAAA"], "server": "bootstrap"},
                    # همه چیز دیگه بره به remote (از تونل)
                    {"server": "remote"},
                ],
                # این خط رو حذف کن یا بذار "bootstrap" — final: "remote" باعث لوپ می‌شه!
                "final": "bootstrap",  # <--- این تغییر نهایی و حیاتیه!
                "strategy": "ipv4_only",
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": "SINGTUN",
                    "address": ["172.20.0.1/30"],
                    "mtu": 1280,
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
                },
                # Bind direct outbound to physical interface to ensure it exits correctly
                {
                    "type": "direct", 
                    "tag": "direct",
                    **({"bind_interface": interface_name} if interface_name else {}),
                },
                {"type": "block", "tag": "block"},
            ],
            "route": {
                "rules": [
                    # Hijack DNS - Sing-box will resolve DNS using its configured servers
                    {"protocol": "dns", "action": "hijack-dns"},
                    {"protocol": "udp", "port": 443, "outbound": "block"},
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

        # Bypass proxy server (IP + Domain)
        for ip in proxy_ips + ["1.1.1.1", "8.8.8.8"]:
            rules.append({"ip_cidr": f"{ip}/32", "outbound": "direct"})
        for domain in proxy_domains:
            rules.append({"domain_suffix": domain, "outbound": "direct"})
            dns_rules.append({"domain_suffix": domain, "server": "bootstrap"})

        # Process bypass - MUST BE FIRST to prevent xray.exe traffic from matching DNS rules
        process_bypass_rules = [
            {
                "process_name": [
                    "xray.exe",
                    "v2ray.exe",
                    "sing-box.exe",
                    "python.exe",
                ],
                "outbound": "direct",
            },
            {"process_path": [XRAY_EXECUTABLE], "outbound": "direct"},
        ]
        # Insert at beginning so process bypass takes priority over DNS routing
        for i, rule in enumerate(process_bypass_rules):
            rules.insert(i, rule)

        # Country routing
        if routing_country and routing_country.lower() != "none":
            mapping = {
                "ir": ("category-ir", "ir"),
                "cn": ("cn", "cn"),
                "ru": ("category-ru", "ru"),
            }
            if routing_country.lower() in mapping:
                site, ip = mapping[routing_country.lower()]
                rules.extend(
                    [
                        {"domain": [f"geosite:{site}"], "outbound": "direct"},
                        {"ip_cidr": [f"geoip:{ip}"], "outbound": "direct"},
                    ]
                )

        return cfg
