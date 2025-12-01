"""VLESS Link Parser — xhttp/splithttp-ready, routing untouched"""
import urllib.parse


class LinkParser:
    """Parses VLESS links into Xray configuration (handles xhttp/splithttp)."""

    @staticmethod
    def parse_vless(link: str) -> dict:
        if not link.startswith("vless://"):
            raise ValueError("Invalid VLESS link")

        parsed = urllib.parse.urlparse(link)

        # UUID + host:port
        if "@" not in parsed.netloc:
            raise ValueError("Invalid VLESS link: missing UUID")
        user_id, host_port = parsed.netloc.split("@", 1)
        if ":" in host_port:
            address, port = host_port.split(":")
            port = int(port)
        else:
            address = host_port
            port = 443

        # parse query params
        params = urllib.parse.parse_qs(parsed.query)
        def get_param(k, default=None):
            v = params.get(k)
            return v[0] if v and len(v) > 0 else default

        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "VLESS Server"

        encryption = get_param("encryption", "none")
        security = get_param("security", "none")
        sni = get_param("sni", address)
        fp = get_param("fp")
        alpn_raw = get_param("alpn")
        allow_insecure = get_param("allowInsecure", get_param("insecure", "0")) == "1"

        # base outbound
        outbound = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": address,
                        "port": port,
                        "users": [
                            {"id": user_id, "encryption": encryption, "flow": get_param("flow", "")}
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": get_param("type", "tcp"),
                "security": security
            }
        }

        # TLS
        if security == "tls":
            tls = {"serverName": sni, "allowInsecure": allow_insecure}
            if alpn_raw:
                tls["alpn"] = [x for x in alpn_raw.split(",") if x]
            if fp:
                tls["fingerprint"] = fp
            outbound["streamSettings"]["tlsSettings"] = tls

        # Reality
        if security == "reality":
            outbound["streamSettings"]["realitySettings"] = {
                "serverName": sni,
                "publicKey": get_param("pbk", ""),
                "shortIds": [s for s in (get_param("sid", "") or "").split(",") if s],
                "fingerprint": fp or "chrome"
            }

        # network-specific
        net = get_param("type", outbound["streamSettings"]["network"])
        if net in ("xhttp", "splithttp"):
            outbound["streamSettings"]["network"] = "splithttp"
            host_param = get_param("host", address)
            outbound["streamSettings"]["splithttpSettings"] = {
                "path": get_param("path", "/"),
                "host": host_param,
                "scMaxEachPostBytes": int(get_param("scMaxEachPostBytes", 0)) or None,
                "scMaxConcurrentPosts": int(get_param("scMaxConcurrentPosts", 0)) or None
            }
            # remove None
            for k in list(outbound["streamSettings"]["splithttpSettings"].keys()):
                if outbound["streamSettings"]["splithttpSettings"][k] is None:
                    del outbound["streamSettings"]["splithttpSettings"][k]

        # other transports
        elif net == "ws":
            outbound["streamSettings"]["wsSettings"] = {"path": get_param("path", "/"), "headers": {"Host": get_param("host", address)}}
        elif net == "grpc":
            outbound["streamSettings"]["grpcSettings"] = {"serviceName": get_param("serviceName", "")}
        elif net in ("http", "httpupgrade"):
            outbound["streamSettings"]["network"] = "http"
            outbound["streamSettings"]["httpSettings"] = {"path": get_param("path", "/"), "host": get_param("host", address)}

        # final config: routing untouched
        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {"tag": "socks", "port": 10808, "listen": "127.0.0.1", "protocol": "socks", "settings": {"udp": True}},
                {"tag": "http", "port": 10809, "listen": "127.0.0.1", "protocol": "http"}
            ],
            "outbounds": [outbound, {"tag": "direct", "protocol": "freedom", "settings": {}}, {"tag": "block", "protocol": "blackhole", "settings": {}}],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": [
                    {"type": "field", "outboundTag": "direct", "ip": ["geoip:private"]},
                    {"type": "field", "outboundTag": "direct", "domain": ["geosite:private"]},
                    {"type": "field", "outboundTag": "block", "domain": ["geosite:category-ads-all"]}
                ]
            }
        }

        return {"name": name, "config": config}
