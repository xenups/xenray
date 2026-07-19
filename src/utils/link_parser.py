"""VLESS Link Parser — xhttp/splithttp-ready, dynamic mapping router"""

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional

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

# ── Dynamic Mapping Router: type system ────────────────────────────

BOOL_TRUE = {"true", "1", "yes"}
BOOL_FALSE = {"false", "0", "no"}

# Comma-separated fields that should be split into lists
SPLIT_FIELDS = {
    "alpn", "sid",
    "fm_tcp_lengths", "fm_tcp_delays",
    "fm_udp_rand", "fm_udp_delay",
}

# XHTTP/SplitHTTP param keys that route into xhttpSettings
XHTTP_PARAMS = {
    "mode", "noSSEHeader", "xPaddingBytes",
    "scStreamUpServerSecs", "scMaxBufferedPosts",
    "scMaxEachPostBytes", "scMaxConcurrentPosts",
    "xmuxMaxConcurrency", "xmuxMaxConnections",
    "xmuxCMaxReuseTimes", "xmuxHMaxReusableSecs", "xmuxHMaxRequestTimes",
}

# Underscore-to-camelCase remapping for FinalMask and QUIC param suffixes
# Ensures URL query params like fm_quic_brutal_up map to JSON key brutalUp
SUFFIX_CAMEL_MAP = {
    "brutal_up": "brutalUp",
    "brutal_down": "brutalDown",
    "max_split": "maxSplit",
    "packet_size": "packetSize",
    "salamander_pwd": "password",
    "sudoku_pwd": "password",
    "sudoku_ascii": "ascii",
    "no_sse": "noSSEHeader",
    "sc_stream_up_server_secs": "scStreamUpServerSecs",
    "sc_max_buffered_posts": "scMaxBufferedPosts",
    "sc_max_each_post_bytes": "scMaxEachPostBytes",
    "sc_max_concurrent_posts": "scMaxConcurrentPosts",
    "xmux_max_concurrency": "xmuxMaxConcurrency",
    "xmux_max_connections": "xmuxMaxConnections",
    "xmux_c_max_reuse_times": "xmuxCMaxReuseTimes",
    "xmux_h_max_reusable_secs": "xmuxHMaxReusableSecs",
    "xmux_h_max_request_times": "xmuxHMaxRequestTimes",
}


def _to_camel(suffix: str) -> str:
    """Convert underscore_separated suffix to camelCase, with known overrides."""
    if suffix in SUFFIX_CAMEL_MAP:
        return SUFFIX_CAMEL_MAP[suffix]
    parts = suffix.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _cast_value(raw: str) -> Any:
    """Type-cast a raw URL query string into the correct Python type."""
    if raw.lower() in BOOL_TRUE:
        return True
    if raw.lower() in BOOL_FALSE:
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        f = float(raw)
        if f == int(f):
            return int(f)
        return f
    except ValueError:
        pass
    return raw


def _maybe_split(key: str, raw: str) -> Any:
    """Split a comma-separated value into a typed list if the key is splittable."""
    stripped = key.removeprefix("fm_tcp_").removeprefix("fm_udp_").removeprefix("fm_quic_")
    if key in SPLIT_FIELDS or stripped in SPLIT_FIELDS:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return [_cast_value(p) for p in parts]
    return _cast_value(raw)


def _route_fm_params(raw_params: Dict[str, str]) -> Dict[str, Any]:
    """
    Route fm_* query params into the finalmask nested structure.

    Routing rules:
      fm_tcp_<suffix>  → finalmask.tcp[0].settings[<suffix>]
      fm_udp_<suffix>  → finalmask.udp[0].settings[<suffix>]
      fm_quic_<suffix> → finalmask.quicParams[<suffix>]

    The first mask of each protocol is created from all matching params.
    """
    finalmask: Dict[str, Any] = {}

    tcp_group: Dict[str, Any] = {}
    udp_group: Dict[str, Any] = {}
    quic_group: Dict[str, Any] = {}

    for key, raw in raw_params.items():
        if key == "fm_tcp_type":
            tcp_group["type"] = raw
        elif key.startswith("fm_tcp_"):
            suffix = _to_camel(key[7:])
            # FinalMask settings are always strings (Int32Range, etc.) — no type casting
            # But comma-separated values always become lists (matches Xray JSON schema)
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            tcp_group.setdefault("settings", {})[suffix] = parts if len(parts) > 1 else raw
        elif key == "fm_udp_type":
            udp_group["type"] = raw
        elif key.startswith("fm_udp_"):
            suffix = _to_camel(key[7:])
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            udp_group.setdefault("settings", {})[suffix] = parts if len(parts) > 1 else raw
        elif key.startswith("fm_quic_"):
            suffix = _to_camel(key[8:])
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            quic_group[suffix] = parts if len(parts) > 1 else raw

    if "type" in tcp_group:
        mask: Dict[str, Any] = {"type": tcp_group["type"]}
        if "settings" in tcp_group:
            mask["settings"] = tcp_group["settings"]
        finalmask["tcp"] = [mask]

    if "type" in udp_group:
        mask = {"type": udp_group["type"]}
        if "settings" in udp_group:
            mask["settings"] = udp_group["settings"]
        finalmask["udp"] = [mask]

    if quic_group:
        finalmask["quicParams"] = quic_group

    return finalmask


def _expand_fm_to_params(finalmask: Dict[str, Any]) -> List[str]:
    """Flatten finalmask JSON back into flat fm_* query params."""

    REVERSE_CAMEL = {v: k for k, v in SUFFIX_CAMEL_MAP.items()}

    def _to_snake(camel: str) -> str:
        return REVERSE_CAMEL.get(camel, camel)

    params: List[str] = []

    for mask in finalmask.get("tcp", []):
        mtype = mask.get("type", "")
        if not mtype:
            continue
        params.append(f"fm_tcp_type={mtype}")
        for sk, sv in mask.get("settings", {}).items():
            key = _to_snake(sk)
            if isinstance(sv, list):
                params.append(f"fm_tcp_{key}={','.join(str(x) for x in sv)}")
            else:
                params.append(f"fm_tcp_{key}={sv}")

    for mask in finalmask.get("udp", []):
        mtype = mask.get("type", "")
        if not mtype:
            continue
        params.append(f"fm_udp_type={mtype}")
        for sk, sv in mask.get("settings", {}).items():
            key = _to_snake(sk)
            if isinstance(sv, list):
                if sk == "noise" and isinstance(sv, list):
                    for item in sv:
                        if isinstance(item, dict):
                            for nk, nv in item.items():
                                params.append(f"fm_udp_{_to_snake(nk)}={nv}")
                else:
                    params.append(f"fm_udp_{key}={','.join(str(x) for x in sv)}")
            else:
                params.append(f"fm_udp_{key}={sv}")

    for qk, qv in finalmask.get("quicParams", {}).items():
        params.append(f"fm_quic_{_to_snake(qk)}={qv}")

    return params


def _route_xhttp_params(raw_params: Dict[str, str]) -> Dict[str, Any]:
    """
    Dynamically collect XHTTP/SplitHTTP parameters into xhttpSettings block.

    Handles XMUX sub-object routing automatically.
    """
    xhttp: Dict[str, Any] = {}
    xmux: Dict[str, Any] = {}

    XMUX_MAP = {
        "xmuxMaxConcurrency": "maxConcurrency",
        "xmuxMaxConnections": "maxConnections",
        "xmuxCMaxReuseTimes": "cMaxReuseTimes",
        "xmuxHMaxReusableSecs": "hMaxReusableSecs",
        "xmuxHMaxRequestTimes": "hMaxRequestTimes",
    }

    for key, raw in raw_params.items():
        if key not in XHTTP_PARAMS:
            continue
        casted = _cast_value(raw)

        if key in XMUX_MAP:
            xmux[XMUX_MAP[key]] = casted
        elif key == "noSSEHeader":
            xhttp[key] = _cast_value(raw)
        else:
            xhttp[key] = casted

    if xmux:
        xhttp["xmux"] = xmux

    return xhttp


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
        # Some clients omit UUID (e.g., when using cert-based auth or custom encryption)
        if "@" in parsed.netloc:
            try:
                user_id, host_port = parsed.netloc.split("@", 1)
            except ValueError as e:
                raise ValueError("Invalid VLESS link: malformed netloc") from e
            if not UUID_PATTERN.match(user_id):
                logger.warning(f"UUID format may be invalid: {user_id}")
        else:
            # No UUID — use a placeholder and treat entire netloc as host:port
            user_id = "00000000-0000-0000-0000-000000000000"
            host_port = parsed.netloc
            logger.debug("VLESS link without UUID — using zero-UUID placeholder")

        if ":" in host_port:
            try:
                address, port_str = host_port.rsplit(":", 1)
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError(f"Invalid port number: {port}")
            except ValueError as e:
                raise ValueError(f"Invalid port in link: {e}") from e
        else:
            address = host_port
            port = DEFAULT_PORT

        if not address:
            raise ValueError("Invalid VLESS link: missing address")

        try:
            raw_params = urllib.parse.parse_qs(parsed.query)
        except Exception as e:
            raise ValueError(f"Failed to parse query parameters: {e}") from e

        def get_param(key: str, default: Optional[str] = None) -> Optional[str]:
            values = raw_params.get(key)
            return values[0] if values and len(values) > 0 else default

        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "VLESS Server"

        encryption = get_param("encryption", DEFAULT_ENCRYPTION)

        security = get_param("security", DEFAULT_SECURITY)
        if security not in VALID_SECURITY:
            logger.warning(f"Unknown security: {security}, using default")
            security = DEFAULT_SECURITY

        sni = get_param("sni")
        fp = get_param("fp")
        flow = get_param("flow", "")
        allow_insecure = get_param("allowInsecure", get_param("insecure", "0")) == "1"

        outbound: Dict[str, Any] = {
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

        network = get_param("type", outbound["streamSettings"]["network"])
        if network not in VALID_NETWORKS:
            logger.warning(f"Unknown network type: {network}, using default")
            network = DEFAULT_NETWORK
            outbound["streamSettings"]["network"] = network

        # ── TLS settings ──
        if security == "tls":
            tls_settings: Dict[str, Any] = {"serverName": sni or address, "allowInsecure": allow_insecure}
            alpn_raw = get_param("alpn")
            if alpn_raw:
                alpn_list = _maybe_split("alpn", alpn_raw)
                if isinstance(alpn_list, list) and alpn_list:
                    tls_settings["alpn"] = alpn_list
            if fp:
                tls_settings["fingerprint"] = fp

            # ECH (Encrypted Client Hello)
            ech = get_param("ech")
            if ech:
                try:
                    ech_decoded = urllib.parse.unquote(ech)
                    tls_settings["echConfigList"] = ech_decoded
                    ech_force = get_param("echForceQuery")
                    if ech_force:
                        tls_settings["echForceQuery"] = _cast_value(ech_force)
                    ech_sockopt_raw = get_param("echSockopt")
                    if ech_sockopt_raw:
                        try:
                            decoded = urllib.parse.unquote(ech_sockopt_raw)
                            ech_sockopt = json.loads(decoded)
                            if isinstance(ech_sockopt, dict):
                                tls_settings["echSockopt"] = ech_sockopt
                        except (json.JSONDecodeError, ValueError):
                            logger.warning(f"Failed to parse echSockopt: {ech_sockopt_raw}")
                    logger.info(f"[TLS] ECH enabled with config: {ech_decoded}")
                except Exception as e:
                    logger.warning(f"Failed to configure ECH: {e}")

            outbound["streamSettings"]["tlsSettings"] = tls_settings

        # ── Reality settings ──
        if security == "reality":
            pbk = get_param("pbk", "")
            sid_raw = get_param("sid", "")

            if not pbk:
                raise ValueError("Reality configuration missing required 'pbk' parameter")
            if not sni:
                raise ValueError("Reality configuration missing required 'sni' parameter")

            reality_settings: Dict[str, Any] = {
                "show": False,
                "serverName": sni,
                "publicKey": pbk,
                "shortIds": _maybe_split("sid", sid_raw) if sid_raw else [""],
                "fingerprint": fp or DEFAULT_FINGERPRINT,
            }
            spx = get_param("spx")
            if spx:
                reality_settings["spiderX"] = spx

            outbound["streamSettings"]["realitySettings"] = reality_settings

        # ── FinalMask (dynamic routing via fm_* prefix + JSON fm param) ──
        flat_params = {k: v[0] for k, v in raw_params.items() if v}
        finalmask = _route_fm_params(flat_params)

        # Support JSON-encoded fm param (v2rayN/Sing-box compatibility)
        fm_json_raw = get_param("fm")
        if fm_json_raw:
            try:
                fm_json = json.loads(urllib.parse.unquote(fm_json_raw))
                if isinstance(fm_json, dict):
                    # Merge: JSON takes precedence over flat fm_* params
                    for key in ("tcp", "udp", "quicParams"):
                        if key in fm_json:
                            finalmask[key] = fm_json[key]
                    logger.info(f"[FinalMask] Applied JSON fm param: {list(fm_json.keys())}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON fm param: {e}")

        if finalmask:
            outbound["streamSettings"]["finalmask"] = finalmask
            logger.info(f"[FinalMask] Configured traffic camouflage: {list(finalmask.keys())}")

        # ── Transport-specific settings ──
        host_param = get_param("host")

        if network in ("xhttp", "splithttp"):
            outbound["streamSettings"]["network"] = "xhttp"

            if not host_param:
                if sni and address != sni:
                    host_param = sni
                else:
                    host_param = address

            xhttp_settings: Dict[str, Any] = {
                "path": get_param("path", DEFAULT_PATH),
                "host": host_param,
            }

            xhttp_dynamic = _route_xhttp_params(flat_params)
            xhttp_settings.update(xhttp_dynamic)

            # Support JSON-encoded extra param (v2rayN compatibility)
            extra_raw = get_param("extra")
            if extra_raw:
                try:
                    extra_json = json.loads(urllib.parse.unquote(extra_raw))
                    if isinstance(extra_json, dict):
                        # Merge with existing — extra JSON values take precedence
                        for ek, ev in extra_json.items():
                            # Convert Xray JSON field names to xhttp param naming
                            # e.g. noSSEHeader from JSON → keep as-is (already camelCase)
                            xhttp_settings[ek] = ev
                        logger.info(f"[XHTTP] Applied extra JSON: {list(extra_json.keys())}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse extra JSON: {e}")

            outbound["streamSettings"]["xhttpSettings"] = xhttp_settings

        elif network == "ws":
            if not host_param:
                if sni and address != sni:
                    host_param = sni
                else:
                    host_param = address
            outbound["streamSettings"]["wsSettings"] = {
                "path": get_param("path", DEFAULT_PATH),
                "headers": {"Host": host_param},
            }

        elif network == "grpc":
            service_name = get_param("serviceName", "")
            outbound["streamSettings"]["grpcSettings"] = {"serviceName": service_name}

        elif network == "httpupgrade":
            outbound["streamSettings"]["network"] = "httpupgrade"
            if not host_param:
                if sni and address != sni:
                    host_param = sni
                else:
                    host_param = address
            outbound["streamSettings"]["httpupgradeSettings"] = {
                "path": get_param("path", DEFAULT_PATH),
                "host": host_param,
            }

        elif network == "http":
            outbound["streamSettings"]["network"] = "http"
            http_settings = {
                "path": get_param("path", DEFAULT_PATH),
                "host": host_param or address,
            }
            outbound["streamSettings"]["httpSettings"] = http_settings

        elif network in ("quic", "h3"):
            outbound["streamSettings"]["network"] = "quic"
            quic_settings: Dict[str, Any] = {
                "security": get_param("quicSecurity", "none"),
                "key": get_param("key", ""),
                "type": get_param("headerType", "none"),
            }
            if quic_settings["security"] == "none" and not quic_settings["key"]:
                quic_settings.pop("key", None)
            if quic_settings["type"] == "none":
                quic_settings.pop("type", None)
            outbound["streamSettings"]["quicSettings"] = quic_settings

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
        fp = data.get("fp", "")

        if security == "auto":
            security = "auto"

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
                ss["tlsSettings"]["alpn"] = _maybe_split("alpn", alpn) if isinstance(_maybe_split("alpn", alpn), list) else [x.strip() for x in alpn.split(",") if x.strip()]
            if fp:
                ss["tlsSettings"]["fingerprint"] = fp

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

        if outbound["streamSettings"]["security"] == "tls":
            tls_settings: Dict[str, Any] = {"serverName": sni, "allowInsecure": allow_insecure}
            fp = get_param("fp")
            if fp:
                tls_settings["fingerprint"] = fp
            alpn_raw = get_param("alpn")
            if alpn_raw:
                alpn_list = _maybe_split("alpn", alpn_raw)
                if isinstance(alpn_list, list) and alpn_list:
                    tls_settings["alpn"] = alpn_list
            outbound["streamSettings"]["tlsSettings"] = tls_settings

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
        """
        Helper to wrap outbound in minimal config structure.

        Note: Inbounds, DNS, and detailed routing are added by XrayConfigProcessor
        based on user settings. This only provides the parsed outbound.
        """
        return {
            "log": {"loglevel": "warning"},
            "inbounds": [],
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
                return ""
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

        params: List[str] = []
        params.append(f"type={network}")
        if security != "none":
            params.append(f"security={security}")
        if flow:
            params.append(f"flow={flow}")
        if encryption and encryption != "none":
            params.append(f"encryption={encryption}")

        if network in ("ws", "xhttp"):
            if network == "ws":
                ws = stream.get("wsSettings", {})
                params.append(f"path={urllib.parse.quote(ws.get('path', '/'))}")
                host = ws.get("headers", {}).get("Host", "")
                if host:
                    params.append(f"host={host}")
            else:  # xhttp
                xh = stream.get("xhttpSettings", {})
                params.append(f"path={urllib.parse.quote(xh.get('path', '/'))}")
                host = xh.get("host", "")
                if host:
                    params.append(f"host={host}")
                # Collect non-core xhttp fields into extra JSON param
                XH_CORE = {"path", "host"}
                extra_fields = {k: v for k, v in xh.items() if k not in XH_CORE}
                if extra_fields:
                    params.append(f"extra={urllib.parse.quote(json.dumps(extra_fields), safe='')}")
                # Mode from extra or direct
                mode = xh.get("mode")
                if mode and "mode" not in extra_fields:
                    params.append(f"mode={mode}")
        elif network == "grpc":
            grpc = stream.get("grpcSettings", {})
            service = grpc.get("serviceName", "")
            if service:
                params.append(f"serviceName={service}")

        if security == "tls":
            tls = stream.get("tlsSettings", {})
            params.append(f"sni={tls.get('serverName', '')}")
            if tls.get("fingerprint"):
                params.append(f"fp={tls.get('fingerprint')}")
            if tls.get("alpn"):
                params.append(f"alpn={','.join(tls['alpn'])}")
            ech = tls.get("echConfigList") or tls.get("echConfig")
            if ech:
                if isinstance(ech, list):
                    ech = ",".join(ech)
                params.append(f"ech={urllib.parse.quote(str(ech), safe='')}")
            ech_sockopt = tls.get("echSockopt")
            if ech_sockopt and isinstance(ech_sockopt, dict):
                params.append(f"echSockopt={urllib.parse.quote(json.dumps(ech_sockopt), safe='')}")
        elif security == "reality":
            reality = stream.get("realitySettings", {})
            params.append(f"sni={reality.get('serverName', '')}")
            params.append(f"pbk={reality.get('publicKey', '')}")
            sid_list = reality.get("shortIds", [])
            params.append(f"sid={','.join(sid_list) if isinstance(sid_list, list) else sid_list}")
            if reality.get("fingerprint"):
                params.append(f"fp={reality.get('fingerprint')}")
            if reality.get("spiderX"):
                params.append(f"spx={reality.get('spiderX')}")

        # FinalMask — prefer JSON fm param when it contains structured data (e.g. noisy array)
        finalmask = stream.get("finalmask", {})
        flat_fm = _expand_fm_to_params(finalmask)
        if flat_fm:
            # Check if flat representation is faithful; otherwise use JSON fm param
            test_fm = _route_fm_params({p.split("=", 1)[0]: p.split("=", 1)[1] for p in flat_fm if "=" in p})
            if test_fm == finalmask:
                params.extend(flat_fm)
            else:
                params.append(f"fm={urllib.parse.quote(json.dumps(finalmask), safe='')}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)
        return f"vless://{uuid}@{address}:{port}?{query}#{fragment}"

    @staticmethod
    def _generate_vmess(outbound: dict, name: str) -> str:
        import base64

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

        params: List[str] = []
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

        obfs = user.get("obfs")
        if obfs:
            params.append(f"obfs={obfs.get('type', 'none')}")
            params.append(f"obfs-password={obfs.get('password', '')}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)
        return f"hysteria2://{password}@{address}:{port}?{query}#{fragment}"
