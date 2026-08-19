"""VMess protocol parser and generator."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict

from src.core.parsers.base import (
    _maybe_split,
    _validate_fingerprint,
    build_minimal_config,
)


class VmessParser:
    """Parses and generates VMess configurations."""

    @staticmethod
    def parse(link: str) -> Dict[str, Any]:
        """Parse VMess link (standard JSON-in-Base64) into Xray configuration."""
        if not link.startswith("vmess://"):
            raise ValueError("Invalid VMess link")

        payload = link[8:]
        try:
            padding = len(payload) % 4
            if padding:
                payload += "=" * (4 - padding)
            decoded = base64.b64decode(payload).decode("utf-8")
            data = json.loads(decoded)
        except Exception as e:
            raise ValueError(f"Failed to decode VMess link: {e}") from e

        name = data.get("ps", "VMess Server")
        address = data.get("add", "")
        try:
            port = int(data.get("port", 443))
        except (ValueError, TypeError):
            port = 443
        uuid = data.get("id", "")
        alter_id = int(data.get("aid", 0))
        security = data.get("scy", "auto")
        network = data.get("net", "tcp")
        header_type = data.get("type", "none")
        host = data.get("host", "")
        path = data.get("path", "")
        tls = data.get("tls", "")
        sni = data.get("sni", "")
        alpn = data.get("alpn", "")
        fp = _validate_fingerprint(data.get("fp", ""))
        cipher_suites = data.get("cipherSuites", "")

        outbound = {
            "tag": "proxy",
            "protocol": "vmess",
            "settings": {
                "vnext": [
                    {
                        "address": address,
                        "port": port,
                        "users": [
                            {
                                "id": uuid,
                                "alterId": alter_id,
                                "security": security,
                            }
                        ],
                    }
                ]
            },
            "streamSettings": {
                "network": network,
                "security": "tls" if tls == "tls" else "none",
            },
        }

        ss = outbound["streamSettings"]

        if ss["security"] == "tls":
            ss["tlsSettings"] = {
                "serverName": sni or host or address,
                "allowInsecure": False,
            }
            if alpn:
                ss["tlsSettings"]["alpn"] = (
                    _maybe_split("alpn", alpn)
                    if isinstance(_maybe_split("alpn", alpn), list)
                    else [x.strip() for x in alpn.split(",") if x.strip()]
                )
            if fp:
                ss["tlsSettings"]["fingerprint"] = fp
            if cipher_suites:
                ss["tlsSettings"]["cipherSuites"] = cipher_suites

        if network == "ws":
            ss["wsSettings"] = {"path": path, "headers": {"Host": host} if host else {}}
        elif network in ("h2", "http"):
            ss["network"] = "http"
            ss["httpSettings"] = {
                "path": path,
                "host": [x.strip() for x in host.split(",")] if host else [],
            }
        elif network == "quic":
            ss["quicSettings"] = {
                "security": host,
                "header": {"type": header_type},
            }
        elif network == "kcp":
            ss["kcpSettings"] = {"header": {"type": header_type}}
        elif network == "grpc":
            ss["grpcSettings"] = {"serviceName": path}

        return {"name": name, "config": build_minimal_config(outbound)}

    @staticmethod
    def generate(outbound: dict, name: str) -> str:
        """Generate a VMess share link from outbound config."""
        settings = outbound.get("settings", {})
        stream = outbound.get("streamSettings", {})
        vnext = settings.get("vnext", [{}])[0]
        user = vnext.get("users", [{}])[0]

        data = {
            "v": "2",
            "ps": name,
            "add": vnext.get("address", ""),
            "port": str(vnext.get("port", 443)),
            "id": user.get("id", ""),
            "aid": str(user.get("alterId", 0)),
            "scy": user.get("security", "auto"),
            "net": stream.get("network", "tcp"),
            "type": "none",
            "host": "",
            "path": "",
            "tls": "",
            "sni": "",
            "alpn": "",
            "fp": "",
        }

        net = data["net"]
        security = stream.get("security", "none")
        if security == "tls":
            data["tls"] = "tls"
            tls = stream.get("tlsSettings", {})
            data["sni"] = tls.get("serverName", "")
            if tls.get("alpn"):
                data["alpn"] = ",".join(tls["alpn"])
            if tls.get("fingerprint"):
                data["fp"] = tls["fingerprint"]
            if tls.get("cipherSuites"):
                data["cipherSuites"] = tls["cipherSuites"]

        if net == "ws":
            ws = stream.get("wsSettings", {})
            data["path"] = ws.get("path", "")
            data["host"] = ws.get("headers", {}).get("Host", "")
        elif net == "grpc":
            grpc = stream.get("grpcSettings", {})
            data["path"] = grpc.get("serviceName", "")

        json_str = json.dumps(data)
        b64 = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        return f"vmess://{b64}"
