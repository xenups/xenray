"""Sing-box Service Manager (fixed for sing-box 1.12+)."""
import json
import os
import subprocess
import time
from typing import Optional
from loguru import logger
import ipaddress
import socket

from src.core.constants import SINGBOX_EXECUTABLE, SINGBOX_CONFIG_PATH, SINGBOX_LOG_FILE, XRAY_EXECUTABLE

class SingboxService:
    """Manages Sing-box TUN process (compatible with sing-box 1.12+)."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._pid: Optional[int] = None
        self._log_handle = None

    def start(
        self,
        xray_socks_port: int,
        routing_country: str = "none",
        proxy_server_ip: list[str] | str = "",
        gateway_ip: str = "",
    ) -> Optional[int]:
        """
        Start Sing-box with a safe config for sing-box v1.12+.
        Returns PID on success, None on failure.
        """
        try:
            config = self._generate_config(
                xray_socks_port, proxy_server_ip, gateway_ip
            )

            os.makedirs(os.path.dirname(SINGBOX_CONFIG_PATH), exist_ok=True)
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            logger.info(f"[SingboxService] Starting sing-box with config {SINGBOX_CONFIG_PATH}")

            os.makedirs(os.path.dirname(SINGBOX_LOG_FILE), exist_ok=True)
            self._log_handle = open(SINGBOX_LOG_FILE, "w", encoding="utf-8")

            cmd = [SINGBOX_EXECUTABLE, "run", "-c", SINGBOX_CONFIG_PATH]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

            self._process = subprocess.Popen(
                cmd,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                text=True,
            )

            time.sleep(1.5)

            if self._process.poll() is not None:
                logger.error("[SingboxService] sing-box exited immediately — check logs")
                self._close_log()
                self._process = None
                self._pid = None
                return None

            self._pid = self._process.pid
            logger.info(f"[SingboxService] sing-box started, PID {self._pid}")
            return self._pid

        except Exception as e:
            logger.exception("[SingboxService] Failed to start sing-box: %s", e)
            self._close_log()
            return None

    def stop(self) -> bool:
        """Stop Sing-box process."""
        try:
            if not self._process:
                return True

            logger.info(f"[SingboxService] Stopping sing-box (PID {self._pid})")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("[SingboxService] Terminate timeout — killing")
                self._process.kill()
                self._process.wait()

            self._process = None
            self._pid = None
            self._close_log()
            logger.info("[SingboxService] sing-box stopped")
            return True

        except Exception as e:
            logger.exception("[SingboxService] Failed to stop sing-box: %s", e)
            return False

    def _close_log(self):
        if self._log_handle:
            try:
                self._log_handle.flush()
            except Exception:
                pass
            try:
                self._log_handle.close()
            except Exception:
                pass
        self._log_handle = None

    def _generate_config(
        self,
        socks_port: int,
        proxy_server_ip: list[str] | str = "",
        gateway_ip: str = ""
    ) -> dict:
        dns_servers = [
            {"tag": "local", "address": "local", "detour": "direct"},
            {"tag": "remote", "address": "local", "detour": "direct"} 
        ]

        cfg = {
            "log": {"level": "info"},
            "dns": {
                "servers": dns_servers,
                "rules": [],
                "final": "remote",
                "strategy": "ipv4_only"
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": "SINGTUN",
                    "address": ["172.20.0.1/30"],
                    "mtu": 1100,
                    "auto_route": True,
                    "strict_route": False,
                    "stack": "gvisor",
                    "endpoint_independent_nat": True,
                    "sniff": True,
                    "sniff_override_destination": True
                }
            ],
            "outbounds": [
                {"type": "socks", "tag": "proxy", "server": "127.0.0.1", "server_port": socks_port},
                {"type": "direct", "tag": "direct"},
                {"type": "block", "tag": "block"}
            ],
            "route": {"rules": [], "final": "proxy"}
        }

        # DNS queries → hijack-dns
        cfg["route"]["rules"].append({"protocol": "dns", "action": "hijack-dns"})

        # Block QUIC (UDP 443) to force TCP
        cfg["route"]["rules"].append({
            "protocol": "udp",
            "port": 443,
            "outbound": "block"
        })

        # Bypass rules as before ...
        # Bypass rules as before ...
        if proxy_server_ip:
            # Handle both single string (legacy) and list of strings
            ips_to_bypass = proxy_server_ip if isinstance(proxy_server_ip, list) else [proxy_server_ip]
            
            for ip in ips_to_bypass:
                if not ip: continue
                try:
                    import ipaddress
                    ipaddress.ip_address(ip)
                    # It's an IP
                    cfg["route"]["rules"].append({"ip_cidr": [f"{ip}/32"], "outbound": "direct"})
                except ValueError:
                    # It's a domain
                    cfg["route"]["rules"].append({"domain": [ip], "outbound": "direct"})
                    cfg["dns"]["rules"].append({"domain": [ip], "server": "local"})
                    
                    # CRITICAL: Resolve domain to IPs and bypass them too
                    # Xray will connect to the IP, not the domain, so we must bypass the IP
                    try:
                        logger.info(f"[SingboxService] Resolving proxy domain {ip} for bypass...")
                        addr_info = socket.getaddrinfo(ip, None, socket.AF_INET)
                        resolved_ips = set(info[4][0] for info in addr_info)
                        for resolved_ip in resolved_ips:
                            cfg["route"]["rules"].append({"ip_cidr": [f"{resolved_ip}/32"], "outbound": "direct"})
                        logger.info(f"[SingboxService] Added bypass for resolved IPs: {resolved_ips}")
                    except Exception as e:
                        logger.warning(f"[SingboxService] Failed to resolve proxy domain {ip} for bypass: {e}")

        if gateway_ip:
            cfg["route"]["rules"].append({"ip_cidr": [f"{gateway_ip}/32"], "outbound": "direct"})

        # Rule: Bypass Xray process to prevent infinite loops
        # Using process_path is more reliable than process_name
        cfg["route"]["rules"].append({
            "process_path": [XRAY_EXECUTABLE], 
            "outbound": "direct"
        })
        
        # Also keep process_name as fallback for other components
        cfg["route"]["rules"].append({
            "process_name": ["python.exe", "xenray.exe", "sing-box.exe"],
            "outbound": "direct"
        })

        cfg["route"]["rules"].append({"ip_cidr": ["1.1.1.1/32", "8.8.8.8/32"], "outbound": "direct"})
        cfg["route"]["rules"].append({"ip_cidr": ["10.0.0.0/8", "192.168.0.0/16", "127.0.0.0/8"], "outbound": "direct"})
        cfg["route"]["rules"].append({"outbound": "proxy"})

        return cfg
