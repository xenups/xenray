"""VLESS Link Parser — xhttp/splithttp-ready, routing untouched"""
import re
import urllib.parse
from typing import Dict, Optional

from loguru import logger

# Constants
DEFAULT_PORT = 443
DEFAULT_NETWORK = "tcp"
DEFAULT_PATH = "/"
DEFAULT_ENCRYPTION = "none"
DEFAULT_SECURITY = "none"
DEFAULT_FINGERPRINT = "chrome"
VALID_NETWORKS = {
    "tcp",
    "ws",
    "grpc",
    "http",
    "httpupgrade",
    "xhttp",
    "splithttp",
    "quic",
    "h3",
}
VALID_SECURITY = {"none", "tls", "reality"}
VALID_ENCRYPTION = {"none", "zero"}
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class LinkParser:
    """Parses VLESS links into Xray configuration (handles xhttp/splithttp)."""

    @staticmethod
    def parse_link(link: str) -> Dict[str, any]:
        """
        Parse any supported link type (vless, vmess, hysteria2).

        Args:
            link: Link string

        Returns:
            Dictionary with 'name' and 'config' keys

        Raises:
            ValueError: If link format is invalid or unsupported
        """
        if not link:
            raise ValueError("Link cannot be empty")

        link = link.strip()
        if link.startswith("vless://"):
            return LinkParser.parse_vless(link)
        elif link.startswith("hysteria2://"):
            return LinkParser.parse_hysteria2(link)
        elif link.startswith("vmess://"):
            return LinkParser.parse_vmess(link)
        elif link.startswith("trojan://"):
            return LinkParser.parse_trojan(link)
        else:
            raise ValueError("Unsupported link protocol")

    @staticmethod
    def parse_vless(link: str) -> Dict[str, any]:
        """
        Parse VLESS link into Xray configuration.

        Args:
            link: VLESS URL string (e.g., "vless://uuid@host:port?params#name")

        Returns:
            Dictionary with 'name' and 'config' keys

        Raises:
            ValueError: If link format is invalid
        """
        if not link or not isinstance(link, str):
            raise ValueError("Link must be a non-empty string")

        link = link.strip()
        if not link.startswith("vless://"):
            raise ValueError("Invalid VLESS link: must start with 'vless://'")

        try:
            parsed = urllib.parse.urlparse(link)
        except Exception as e:
            raise ValueError(f"Failed to parse URL: {e}") from e

        # Validate and extract UUID + host:port
        if "@" not in parsed.netloc:
            raise ValueError("Invalid VLESS link: missing UUID or '@' separator")

        try:
            user_id, host_port = parsed.netloc.split("@", 1)
        except ValueError as e:
            raise ValueError("Invalid VLESS link: malformed netloc") from e

        # Validate UUID format
        if not UUID_PATTERN.match(user_id):
            logger.warning(f"UUID format may be invalid: {user_id}")

        # Parse host and port
        if ":" in host_port:
            try:
                address, port_str = host_port.rsplit(":", 1)  # Use rsplit to handle IPv6
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError(f"Invalid port number: {port}")
            except ValueError as e:
                raise ValueError(f"Invalid port in link: {e}") from e
        else:
            address = host_port
            port = DEFAULT_PORT

        # Validate address
        if not address:
            raise ValueError("Invalid VLESS link: missing address")

        # Parse query parameters
        try:
            params = urllib.parse.parse_qs(parsed.query)
        except Exception as e:
            raise ValueError(f"Failed to parse query parameters: {e}") from e

        def get_param(key: str, default: Optional[str] = None) -> Optional[str]:
            """Get first value of query parameter."""
            values = params.get(key)
            return values[0] if values and len(values) > 0 else default

        # Extract name from fragment
        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "VLESS Server"

        # Extract and validate parameters
        encryption = get_param("encryption", DEFAULT_ENCRYPTION)
        # Relaxed encryption validation to support custom types

        security = get_param("security", DEFAULT_SECURITY)
        if security not in VALID_SECURITY:
            logger.warning(f"Unknown security: {security}, using default")
            security = DEFAULT_SECURITY

        sni = get_param("sni") or address
        fp = get_param("fp")
        alpn_raw = get_param("alpn")
        flow = get_param("flow", "")
        allow_insecure = get_param("allowInsecure", get_param("insecure", "0")) == "1"

        # Build base outbound
        outbound = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": address,
                        "port": port,
                        "users": [{"id": user_id, "encryption": encryption, "flow": flow}],
                    }
                ]
            },
            "streamSettings": {
                "network": get_param("type", DEFAULT_NETWORK),
                "security": security,
            },
        }

        # Configure TLS settings
        if security == "tls":
            tls_settings = {"serverName": sni, "allowInsecure": allow_insecure}
            if alpn_raw:
                alpn_list = [x.strip() for x in alpn_raw.split(",") if x.strip()]
                if alpn_list:
                    tls_settings["alpn"] = alpn_list
            if fp:
                tls_settings["fingerprint"] = fp
            outbound["streamSettings"]["tlsSettings"] = tls_settings

        # Configure Reality settings
        if security == "reality":
            pbk = get_param("pbk", "")
            sid = get_param("sid", "")
            if not pbk:
                logger.warning("Reality security requires 'pbk' parameter")

            reality_settings = {
                "serverName": sni,
                "publicKey": pbk,
                "shortIds": [s.strip() for s in sid.split(",") if s.strip()] if sid else [],
                "fingerprint": fp or DEFAULT_FINGERPRINT,
            }
            outbound["streamSettings"]["realitySettings"] = reality_settings

        # Configure network-specific settings
        network = get_param("type", outbound["streamSettings"]["network"])
        if network not in VALID_NETWORKS:
            logger.warning(f"Unknown network type: {network}, using default")
            network = DEFAULT_NETWORK

        # Handle splithttp/xhttp (new in Xray 1.8.0+)
        if network in ("xhttp", "splithttp"):
            outbound["streamSettings"]["network"] = "splithttp"
            host_param = get_param("host") or address
            splithttp_settings = {
                "path": get_param("path", DEFAULT_PATH),
                "host": host_param,
            }

            # Optional parameters
            sc_max_each = get_param("scMaxEachPostBytes")
            sc_max_concurrent = get_param("scMaxConcurrentPosts")

            if sc_max_each:
                try:
                    value = int(sc_max_each)
                    if value > 0:
                        splithttp_settings["scMaxEachPostBytes"] = value
                except ValueError:
                    logger.warning(f"Invalid scMaxEachPostBytes: {sc_max_each}")

            if sc_max_concurrent:
                try:
                    value = int(sc_max_concurrent)
                    if value > 0:
                        splithttp_settings["scMaxConcurrentPosts"] = value
                except ValueError:
                    logger.warning(f"Invalid scMaxConcurrentPosts: {sc_max_concurrent}")

            outbound["streamSettings"]["splithttpSettings"] = splithttp_settings

        # WebSocket transport
        elif network == "ws":
            ws_settings = {
                "path": get_param("path", DEFAULT_PATH),
                "headers": {"Host": get_param("host") or address},
            }
            outbound["streamSettings"]["wsSettings"] = ws_settings

        # gRPC transport
        elif network == "grpc":
            service_name = get_param("serviceName", "")
            grpc_settings = {"serviceName": service_name}
            outbound["streamSettings"]["grpcSettings"] = grpc_settings

        # HTTPUpgrade transport (new in Xray 1.8.0+)
        elif network == "httpupgrade":
            outbound["streamSettings"]["network"] = "httpupgrade"
            httpupgrade_settings = {
                "path": get_param("path", DEFAULT_PATH),
                "host": get_param("host") or address,
            }
            outbound["streamSettings"]["httpupgradeSettings"] = httpupgrade_settings

        # HTTP transport
        elif network == "http":
            outbound["streamSettings"]["network"] = "http"
            http_settings = {
                "path": get_param("path", DEFAULT_PATH),
                "host": get_param("host") or address,
            }
            outbound["streamSettings"]["httpSettings"] = http_settings

        # QUIC/H3 transport (HTTP/3 over QUIC)
        elif network in ("quic", "h3"):
            outbound["streamSettings"]["network"] = "quic"
            quic_settings = {
                "security": get_param("quicSecurity", "none"),
                "key": get_param("key", ""),
                "type": get_param("headerType", "none"),
            }

            # Remove empty key if security is none
            if quic_settings["security"] == "none" and not quic_settings["key"]:
                quic_settings.pop("key", None)

            # Remove type if it's "none"
            if quic_settings["type"] == "none":
                quic_settings.pop("type", None)

            outbound["streamSettings"]["quicSettings"] = quic_settings

        # TCP transport (default) - no additional settings needed

        return {"name": name, "config": LinkParser._build_config(outbound)}

    @staticmethod
    def parse_hysteria2(link: str) -> Dict[str, any]:
        """
        Parse Hysteria2 link into Xray configuration.
        Format: hysteria2://password@host:port?params#name
        """
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
                "tlsSettings": {"serverName": sni, "allowInsecure": insecure},
            },
        }

        if obfs_type and obfs_type != "none" and obfs_password:
            outbound["settings"]["vnext"][0]["users"][0]["obfs"] = {
                "type": obfs_type,
                "password": obfs_password,
            }

        return {"name": name, "config": LinkParser._build_config(outbound)}

    @staticmethod
    def parse_vmess(link: str) -> Dict[str, any]:
        """
        Parse VMess link into Xray configuration.
        Supports standard JSON-in-Base64 format.
        """
        import base64
        import json

        if not link.startswith("vmess://"):
            raise ValueError("Invalid VMess link")

        payload = link[8:]
        try:
            # Fix base64 padding if needed
            padding = len(payload) % 4
            if padding:
                payload += "=" * (4 - padding)

            decoded = base64.b64decode(payload).decode("utf-8")
            data = json.loads(decoded)
        except Exception as e:
            raise ValueError(f"Failed to decode VMess link: {e}") from e

        # Extract fields from VMess JSON standard
        # v: version
        # ps: name
        # add: address
        # port: port
        # id: uuid
        # aid: alterId
        # scy: security (auto/aes-128-gcm/chacha20-poly1305/none)
        # net: network (tcp/kcp/ws/h2/quic)
        # header type (none/http/srtp/utp/wechat-video/dtls/wireguard) -> for kcp/quic
        # host: host/sni
        # path: path
        # tls: tls ("" or "tls")
        # sni: sni
        # alpn: alpn

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
        fp = data.get("fp", "")  # some clients use fp

        # Normalize security
        if security == "auto":
            security = "auto"  # xray supports "auto" for vmess

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

        # Stream Settings configuration
        # Reuse logic similar to VLESS for transports if possible, or reimplement
        # For simplicity and correctness with VMess JSON format quirks, we implement directly

        ss = outbound["streamSettings"]

        # TLS
        if ss["security"] == "tls":
            ss["tlsSettings"] = {
                "serverName": sni or host or address,
                "allowInsecure": False,  # Defaults
            }
            if alpn:
                ss["tlsSettings"]["alpn"] = [x.strip() for x in alpn.split(",")]
            if fp:
                ss["tlsSettings"]["fingerprint"] = fp

        # Transports
        if network == "ws":
            ss["wsSettings"] = {"path": path, "headers": {"Host": host} if host else {}}
        elif network in ("h2", "http"):  # h2 is http in xray
            ss["network"] = "http"
            ss["httpSettings"] = {
                "path": path,
                "host": [x.strip() for x in host.split(",")] if host else [],
            }
        elif network == "quic":
            ss["quicSettings"] = {
                "security": host,  # confused usage in some vmess links, but usually host field maps to quic security
                "header": {"type": header_type},
            }
        elif network == "kcp":
            ss["kcpSettings"] = {"header": {"type": header_type}}
        elif network == "grpc":
            ss["grpcSettings"] = {"serviceName": path}  # often path is used for serviceName in vmess json
            if data.get("authority"):  # custom field sometimes
                # ss["grpcSettings"]["authority"] = ... # Xray doesn't strictly need authority for client usually
                pass

        return {"name": name, "config": LinkParser._build_config(outbound)}

    @staticmethod
    def parse_trojan(link: str) -> Dict[str, any]:
        """
        Parse Trojan link into Xray configuration.
        Format: trojan://password@host:port?params#name
        """
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

        # TLS Configuration
        if outbound["streamSettings"]["security"] == "tls":
            tls_settings = {"serverName": sni, "allowInsecure": allow_insecure}
            fp = get_param("fp")
            if fp:
                tls_settings["fingerprint"] = fp
            alpn_raw = get_param("alpn")
            if alpn_raw:
                alpn_list = [x.strip() for x in alpn_raw.split(",") if x.strip()]
                if alpn_list:
                    tls_settings["alpn"] = alpn_list
            outbound["streamSettings"]["tlsSettings"] = tls_settings

        # Network Transports
        network = outbound["streamSettings"]["network"]
        if network == "ws":
            outbound["streamSettings"]["wsSettings"] = {
                "path": get_param("path", "/"),
                "headers": {"Host": get_param("host") or address},
            }
        elif network == "grpc":
            outbound["streamSettings"]["grpcSettings"] = {"serviceName": get_param("serviceName", "")}

        return {"name": name, "config": LinkParser._build_config(outbound)}

    @staticmethod
    def _build_config(outbound: Dict) -> Dict:
        """Helper to wrap outbound in full config structure."""
        return {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks",
                    "port": 10805,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"udp": True},
                },
                {
                    "tag": "http",
                    "port": 10809,
                    "listen": "127.0.0.1",
                    "protocol": "http",
                },
            ],
            "outbounds": [
                outbound,
                {"tag": "direct", "protocol": "freedom", "settings": {}},
                {"tag": "block", "protocol": "blackhole", "settings": {}},
            ],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": [
                    {"type": "field", "outboundTag": "direct", "ip": ["geoip:private"]},
                    {
                        "type": "field",
                        "outboundTag": "direct",
                        "domain": ["geosite:private"],
                    },
                    {
                        "type": "field",
                        "outboundTag": "block",
                        "domain": ["geosite:category-ads-all"],
                    },
                ],
            },
        }

    @staticmethod
    def generate_link(config: dict, name: str) -> str:
        """
        Generate a shareable link from Xray config.
        """
        try:
            outbounds = config.get("outbounds", [])
            proxy_out = next((o for o in outbounds if o.get("tag") == "proxy"), None)

            if not proxy_out:
                # Fallback: try first outbound
                if outbounds:
                    proxy_out = outbounds[0]

            if not proxy_out:
                return ""

            protocol = proxy_out.get("protocol")
            if protocol == "vless":
                return LinkParser._generate_vless(proxy_out, name)
            elif protocol == "vmess":
                return LinkParser._generate_vmess(proxy_out, name)
            elif protocol == "trojan":
                return LinkParser._generate_trojan(proxy_out, name)
            elif protocol == "hysteria2":
                return LinkParser._generate_hysteria2(proxy_out, name)
            else:
                return ""  # Unsupported
        except Exception as e:
            logger.error(f"Failed to generate link: {e}")
            return ""

    @staticmethod
    def _generate_vless(outbound: dict, name: str) -> str:
        settings = outbound.get("settings", {})
        stream = outbound.get("streamSettings", {})
        vnext = settings.get("vnext", [{}])[0]
        user = vnext.get("users", [{}])[0]

        uuid = user.get("id", "")
        address = vnext.get("address", "")
        port = vnext.get("port", 443)
        flow = user.get("flow", "")
        encryption = user.get("encryption", "none")

        security = stream.get("security", "none")
        network = stream.get("network", "tcp")

        params = []
        params.append(f"type={network}")
        if security != "none":
            params.append(f"security={security}")
        if flow:
            params.append(f"flow={flow}")
        if encryption and encryption != "none":
            params.append(f"encryption={encryption}")

        # Stream specific
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

        # Security specific
        if security == "tls":
            tls = stream.get("tlsSettings", {})
            params.append(f"sni={tls.get('serverName', '')}")
            if tls.get("fingerprint"):
                params.append(f"fp={tls.get('fingerprint')}")
            if tls.get("alpn"):
                params.append(f"alpn={','.join(tls['alpn'])}")
        elif security == "reality":
            reality = stream.get("realitySettings", {})
            params.append(f"sni={reality.get('serverName', '')}")
            params.append(f"pbk={reality.get('publicKey', '')}")
            params.append(f"sid={','.join(reality.get('shortIds', []))}")
            if reality.get("fingerprint"):
                params.append(f"fp={reality.get('fingerprint')}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)

        return f"vless://{uuid}@{address}:{port}?{query}#{fragment}"

    @staticmethod
    def _generate_vmess(outbound: dict, name: str) -> str:
        # VMess uses base64 encoded JSON
        import base64
        import json

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
            "type": "none",  # Default
            "host": "",
            "path": "",
            "tls": "",
            "sni": "",
            "alpn": "",
        }

        net = data["net"]
        security = stream.get("security", "none")
        if security == "tls":
            data["tls"] = "tls"
            tls = stream.get("tlsSettings", {})
            data["sni"] = tls.get("serverName", "")
            if tls.get("alpn"):
                data["alpn"] = ",".join(tls["alpn"])

        if net == "ws":
            ws = stream.get("wsSettings", {})
            data["path"] = ws.get("path", "")
            data["host"] = ws.get("headers", {}).get("Host", "")
        elif net == "grpc":
            grpc = stream.get("grpcSettings", {})
            data["path"] = grpc.get("serviceName", "")

        # Encode
        json_str = json.dumps(data)
        b64 = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        return f"vmess://{b64}"

    @staticmethod
    def _generate_trojan(outbound: dict, name: str) -> str:
        settings = outbound.get("settings", {})
        stream = outbound.get("streamSettings", {})
        server = settings.get("servers", [{}])[0]

        password = server.get("password", "")
        address = server.get("address", "")
        port = server.get("port", 443)

        security = stream.get("security", "none")
        network = stream.get("network", "tcp")

        params = []
        params.append(f"type={network}")
        if security != "none":
            params.append(f"security={security}")

        if security == "tls":
            tls = stream.get("tlsSettings", {})
            params.append(f"sni={tls.get('serverName', '')}")

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

    @staticmethod
    def _generate_hysteria2(outbound: dict, name: str) -> str:
        settings = outbound.get("settings", {})
        stream = outbound.get("streamSettings", {})
        # Not fully implementing reverse gen for hysteria right now unless needed
        # Basic implementation
        server = settings.get("vnext", [{}])[0]
        address = server.get("address", "")
        port = server.get("port", 443)
        user = server.get("users", [{}])[0]
        password = user.get("password", "")

        tls = stream.get("tlsSettings", {})
        sni = tls.get("serverName", "")
        insecure = "1" if tls.get("allowInsecure") else "0"

        params = []
        if sni:
            params.append(f"sni={sni}")
        if insecure == "1":
            params.append("insecure=1")

        obfs = user.get("obfs")
        if obfs:
            params.append(f"obfs={obfs.get('type', 'none')}")
            params.append(f"obfs-password={obfs.get('password', '')}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)
        return f"hysteria2://{password}@{address}:{port}?{query}#{fragment}"
