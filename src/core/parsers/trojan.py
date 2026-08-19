"""Trojan protocol parser and generator."""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from src.core.parsers.base import (
    DEFAULT_NETWORK,
    DEFAULT_PORT,
    _get_cipher_suites,
    _maybe_split,
    _validate_fingerprint,
    build_minimal_config,
)


class TrojanParser:
    """Parses and generates Trojan configurations."""

    @staticmethod
    def parse(link: str) -> Dict[str, Any]:
        """Parse Trojan link into Xray configuration."""
        if not link.startswith("trojan://"):
            raise ValueError("Invalid Trojan link")

        try:
            parsed = urllib.parse.urlparse(link)
        except Exception as e:
            raise ValueError(f"Failed to parse URL: {e}") from e

        if "@" in parsed.netloc:
            password, host_port = parsed.netloc.split("@", 1)
        else:
            raise ValueError("Invalid Trojan link: missing password")

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

        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "Trojan Server"

        sni = get_param("sni") or get_param("peer") or address
        allow_insecure = get_param("allowInsecure", get_param("insecure", "0")) == "1"

        outbound = {
            "tag": "proxy",
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": address,
                        "port": port,
                        "password": password,
                    }
                ]
            },
            "streamSettings": {
                "network": get_param("type", DEFAULT_NETWORK),
                "security": get_param("security", "tls"),
            },
        }

        if outbound["streamSettings"]["security"] == "tls":
            tls_settings: Dict[str, Any] = {
                "serverName": sni,
                "allowInsecure": allow_insecure,
            }
            fp = _validate_fingerprint(get_param("fp") or "")
            if fp:
                tls_settings["fingerprint"] = fp
            alpn_raw = get_param("alpn")
            if alpn_raw:
                alpn_list = _maybe_split("alpn", alpn_raw)
                if isinstance(alpn_list, list) and alpn_list:
                    tls_settings["alpn"] = alpn_list
            cipher = _get_cipher_suites(get_param)
            if cipher:
                tls_settings["cipherSuites"] = cipher
            outbound["streamSettings"]["tlsSettings"] = tls_settings

        network = outbound["streamSettings"]["network"]
        if network == "ws":
            outbound["streamSettings"]["wsSettings"] = {
                "path": get_param("path", "/"),
                "headers": {"Host": get_param("host") or address},
            }
        elif network == "grpc":
            outbound["streamSettings"]["grpcSettings"] = {"serviceName": get_param("serviceName", "")}

        return {"name": name, "config": build_minimal_config(outbound)}

    @staticmethod
    def generate(outbound: dict, name: str) -> str:
        """Generate a Trojan share link from outbound config."""
        settings = outbound.get("settings", {})
        stream = outbound.get("streamSettings", {})
        server = settings.get("servers", [{}])[0]

        password = server.get("password", "")
        address = server.get("address", "")
        port = server.get("port", 443)

        security = stream.get("security", "none")
        network = stream.get("network", "tcp")

        params: List[str] = []
        params.append(f"type={network}")
        if security != "none":
            params.append(f"security={security}")

        if security == "tls":
            tls = stream.get("tlsSettings", {})
            params.append(f"sni={tls.get('serverName', '')}")
            if tls.get("cipherSuites"):
                params.append(f"cs={tls['cipherSuites']}")

        if network == "ws":
            ws = stream.get("wsSettings", {})
            params.append(f"path={urllib.parse.quote(ws.get('path', '/'))}")
            host = ws.get("headers", {}).get("Host", "")
            if host:
                params.append(f"host={host}")
        elif network == "grpc":
            grpc = stream.get("grpcSettings", {})
            service = grpc.get("serviceName", "")
            if service:
                params.append(f"serviceName={service}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)
        return f"trojan://{password}@{address}:{port}?{query}#{fragment}"
