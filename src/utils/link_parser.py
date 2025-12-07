"""VLESS Link Parser — xhttp/splithttp-ready, routing untouched"""
import urllib.parse
import re
from typing import Dict, Optional
from loguru import logger

# Constants
DEFAULT_PORT = 443
DEFAULT_NETWORK = "tcp"
DEFAULT_PATH = "/"
DEFAULT_ENCRYPTION = "none"
DEFAULT_SECURITY = "none"
DEFAULT_FINGERPRINT = "chrome"
VALID_NETWORKS = {"tcp", "ws", "grpc", "http", "httpupgrade", "xhttp", "splithttp", "quic", "h3"}
VALID_SECURITY = {"none", "tls", "reality"}
VALID_ENCRYPTION = {"none", "zero"}
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


class LinkParser:
    """Parses VLESS links into Xray configuration (handles xhttp/splithttp)."""

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
        if encryption not in VALID_ENCRYPTION:
            logger.warning(f"Unknown encryption: {encryption}, using default")
            encryption = DEFAULT_ENCRYPTION
        
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
                        "users": [
                            {
                                "id": user_id,
                                "encryption": encryption,
                                "flow": flow
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": get_param("type", DEFAULT_NETWORK),
                "security": security
            }
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
                "fingerprint": fp or DEFAULT_FINGERPRINT
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
                "host": host_param
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
                "headers": {
                    "Host": get_param("host") or address
                }
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
                "host": get_param("host") or address
            }
            outbound["streamSettings"]["httpupgradeSettings"] = httpupgrade_settings

        # HTTP transport
        elif network == "http":
            outbound["streamSettings"]["network"] = "http"
            http_settings = {
                "path": get_param("path", DEFAULT_PATH),
                "host": get_param("host") or address
            }
            outbound["streamSettings"]["httpSettings"] = http_settings

        # QUIC/H3 transport (HTTP/3 over QUIC)
        elif network in ("quic", "h3"):
            outbound["streamSettings"]["network"] = "quic"
            quic_settings = {
                "security": get_param("quicSecurity", "none"),
                "key": get_param("key", ""),
                "type": get_param("headerType", "none")
            }
            
            # Remove empty key if security is none
            if quic_settings["security"] == "none" and not quic_settings["key"]:
                quic_settings.pop("key", None)
            
            # Remove type if it's "none"
            if quic_settings["type"] == "none":
                quic_settings.pop("type", None)
            
            outbound["streamSettings"]["quicSettings"] = quic_settings

        # TCP transport (default) - no additional settings needed

        # Build final configuration
        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks",
                    "port": 10808,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"udp": True}
                },
                {
                    "tag": "http",
                    "port": 10809,
                    "listen": "127.0.0.1",
                    "protocol": "http"
                }
            ],
            "outbounds": [
                outbound,
                {
                    "tag": "direct",
                    "protocol": "freedom",
                    "settings": {}
                },
                {
                    "tag": "block",
                    "protocol": "blackhole",
                    "settings": {}
                }
            ],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": [
                    {
                        "type": "field",
                        "outboundTag": "direct",
                        "ip": ["geoip:private"]
                    },
                    {
                        "type": "field",
                        "outboundTag": "direct",
                        "domain": ["geosite:private"]
                    },
                    {
                        "type": "field",
                        "outboundTag": "block",
                        "domain": ["geosite:category-ads-all"]
                    }
                ]
            }
        }

        return {"name": name, "config": config}
