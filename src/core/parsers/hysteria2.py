"""Hysteria2 protocol parser and generator."""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from src.core.parsers.base import (
    DEFAULT_PORT,
    _get_cipher_suites,
    build_minimal_config,
)


class Hysteria2Parser:
    """Parses and generates Hysteria2 configurations."""

    @staticmethod
    def parse(link: str) -> Dict[str, Any]:
        """Parse Hysteria2 link into Xray configuration."""
        if not link.startswith("hysteria2://"):
            raise ValueError("Invalid Hysteria2 link")

        try:
            parsed = urllib.parse.urlparse(link)
        except Exception as e:
            raise ValueError(f"Failed to parse URL: {e}") from e

        if "@" in parsed.netloc:
            password, host_port = parsed.netloc.split("@", 1)
        else:
            raise ValueError("Invalid Hysteria2 link: missing password")

        if ":" in host_port:
            address, port_str = host_port.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = DEFAULT_PORT
        else:
            address = host_port
            port = DEFAULT_PORT

        params = urllib.parse.parse_qs(parsed.query)

        def get_param(key: str, default: Optional[str] = None) -> Optional[str]:
            val = params.get(key)
            return val[0] if val and len(val) > 0 else default

        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "Hysteria2 Server"

        sni = get_param("sni") or get_param("peer") or address
        insecure = get_param("insecure") == "1" or get_param("allowInsecure") == "1"
        obfs_type = get_param("obfs", "none")
        obfs_password = get_param("obfs-password", "")

        tls_settings: Dict[str, Any] = {"serverName": sni, "allowInsecure": insecure}
        cipher = _get_cipher_suites(get_param)
        if cipher:
            tls_settings["cipherSuites"] = cipher

        outbound = {
            "tag": "proxy",
            "protocol": "hysteria2",
            "settings": {
                "vnext": [
                    {
                        "address": address,
                        "port": port,
                        "users": [{"password": password}],
                    }
                ]
            },
            "streamSettings": {
                "security": "tls",
                "tlsSettings": tls_settings,
            },
        }

        if obfs_type and obfs_type != "none" and obfs_password:
            outbound["settings"]["vnext"][0]["users"][0]["obfs"] = {
                "type": obfs_type,
                "password": obfs_password,
            }

        return {"name": name, "config": build_minimal_config(outbound)}

    @staticmethod
    def generate(outbound: dict, name: str) -> str:
        """Generate a Hysteria2 share link from outbound config."""
        settings = outbound.get("settings", {})
        stream = outbound.get("streamSettings", {})
        server = settings.get("vnext", [{}])[0]
        address = server.get("address", "")
        port = server.get("port", 443)
        user = server.get("users", [{}])[0]
        password = user.get("password", "")

        tls = stream.get("tlsSettings", {})
        sni = tls.get("serverName", "")
        insecure = "1" if tls.get("allowInsecure") else "0"

        params: List[str] = []
        if sni:
            params.append(f"sni={sni}")
        if insecure == "1":
            params.append("insecure=1")
        if tls.get("cipherSuites"):
            params.append(f"cs={tls['cipherSuites']}")

        obfs = user.get("obfs")
        if obfs:
            params.append(f"obfs={obfs.get('type', 'none')}")
            params.append(f"obfs-password={obfs.get('password', '')}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)
        return f"hysteria2://{password}@{address}:{port}?{query}#{fragment}"
