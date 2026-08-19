"""VLESS protocol parser and generator."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, List, Optional

from loguru import logger

from src.core.parsers.base import (
    DEFAULT_ENCRYPTION,
    DEFAULT_FINGERPRINT,
    DEFAULT_NETWORK,
    DEFAULT_PATH,
    DEFAULT_PORT,
    DEFAULT_SECURITY,
    UUID_PATTERN,
    VALID_NETWORKS,
    VALID_SECURITY,
    _cast_value,
    _expand_fm_to_params,
    _get_cipher_suites,
    _maybe_split,
    _nest_xhttp_extra,
    _route_fm_params,
    _route_xhttp_params,
    _validate_fingerprint,
    build_minimal_config,
)


class VlessParser:
    """Parses and generates VLESS configurations."""

    @staticmethod
    def parse(link: str) -> Dict[str, Any]:
        """Parse VLESS link into Xray configuration."""
        if not link or not isinstance(link, str):
            raise ValueError("Link must be a non-empty string")

        link = link.strip()
        if not link.startswith("vless://"):
            raise ValueError("Invalid VLESS link: must start with 'vless://'")

        try:
            parsed = urllib.parse.urlparse(link)
        except Exception as e:
            raise ValueError(f"Failed to parse URL: {e}") from e

        if "@" in parsed.netloc:
            try:
                user_id, host_port = parsed.netloc.split("@", 1)
            except ValueError as e:
                raise ValueError("Invalid VLESS link: malformed netloc") from e
            if not UUID_PATTERN.match(user_id):
                logger.warning(f"UUID format may be invalid: {user_id}")
        else:
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
        fp = _validate_fingerprint(get_param("fp") or "")
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

        # TLS settings
        if security == "tls":
            tls_settings: Dict[str, Any] = {
                "serverName": sni or address,
                "allowInsecure": allow_insecure,
            }
            alpn_raw = get_param("alpn")
            if alpn_raw:
                alpn_list = _maybe_split("alpn", alpn_raw)
                if isinstance(alpn_list, list) and alpn_list:
                    tls_settings["alpn"] = alpn_list
            if fp:
                tls_settings["fingerprint"] = fp
            cipher = _get_cipher_suites(get_param)
            if cipher:
                tls_settings["cipherSuites"] = cipher

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

        # Reality settings
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
            cipher = _get_cipher_suites(get_param)
            if cipher:
                reality_settings["cipherSuites"] = cipher

            outbound["streamSettings"]["realitySettings"] = reality_settings

        # FinalMask
        flat_params = {k: v[0] for k, v in raw_params.items() if v}
        finalmask = _route_fm_params(flat_params)

        fm_json_raw = get_param("fm")
        if fm_json_raw:
            try:
                fm_json = json.loads(urllib.parse.unquote(fm_json_raw))
                if isinstance(fm_json, dict):
                    for key in ("tcp", "udp", "quicParams"):
                        if key in fm_json:
                            finalmask[key] = fm_json[key]
                    logger.info(f"[FinalMask] Applied JSON fm param: {list(fm_json.keys())}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON fm param: {e}")

        if finalmask:
            outbound["streamSettings"]["finalmask"] = finalmask
            logger.info(f"[FinalMask] Configured traffic camouflage: {list(finalmask.keys())}")

        # Transport-specific settings
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

            extra_raw = get_param("extra")
            if extra_raw:
                try:
                    extra_json = json.loads(urllib.parse.unquote(extra_raw))
                    if isinstance(extra_json, dict):
                        xhttp_settings["extra"] = extra_json
                        logger.info(f"[XHTTP] Applied extra JSON: {list(extra_json.keys())}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse extra JSON: {e}")

            _nest_xhttp_extra(xhttp_settings)
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
            outbound["streamSettings"]["httpSettings"] = {
                "path": get_param("path", DEFAULT_PATH),
                "host": host_param or address,
            }

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

        return {"name": name, "config": build_minimal_config(outbound)}

    @staticmethod
    def generate(outbound: dict, name: str) -> str:
        """Generate a VLESS share link from outbound config."""
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
                mode = xh.get("mode")
                if mode:
                    params.append(f"mode={mode}")
                extra = xh.get("extra")
                if extra:
                    params.append(f"extra={urllib.parse.quote(json.dumps(extra), safe='')}")
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
            if tls.get("cipherSuites"):
                params.append(f"cs={tls['cipherSuites']}")
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
            if reality.get("cipherSuites"):
                params.append(f"cs={reality['cipherSuites']}")

        finalmask = stream.get("finalmask", {})
        flat_fm = _expand_fm_to_params(finalmask)
        if flat_fm:
            test_fm = _route_fm_params({p.split("=", 1)[0]: p.split("=", 1)[1] for p in flat_fm if "=" in p})
            if test_fm == finalmask:
                params.extend(flat_fm)
            else:
                params.append(f"fm={urllib.parse.quote(json.dumps(finalmask), safe='')}")

        query = "&".join(params)
        fragment = urllib.parse.quote(name)
        return f"vless://{uuid}@{address}:{port}?{query}#{fragment}"
