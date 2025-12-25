import base64
import json

import pytest

from src.utils.link_parser import LinkParser


class TestLinkParser:
    def test_parse_vless_ipv6(self):
        """Test VLESS link with IPv6 address."""
        link = "vless://uuid@[2001:db8::1]:8443?type=tcp#IPv6Server"
        result = LinkParser.parse_link(link)
        assert result["name"] == "IPv6Server"
        assert result["config"]["outbounds"][0]["settings"]["vnext"][0]["address"] == "[2001:db8::1]"
        assert result["config"]["outbounds"][0]["settings"]["vnext"][0]["port"] == 8443

    def test_parse_vless_defaults(self):
        """Test VLESS link with default port and unknown security."""
        link = "vless://uuid@example.com?security=unknown"
        result = LinkParser.parse_link(link)
        assert result["config"]["outbounds"][0]["settings"]["vnext"][0]["port"] == 443
        assert result["config"]["outbounds"][0]["streamSettings"]["security"] == "none"

    def test_parse_vless_tls_details(self):
        """Test VLESS with complex TLS settings (alpn, fp, insecure)."""
        link = "vless://uuid@host:443?security=tls&alpn=h2,http/1.1&fp=chrome&insecure=1#ComplexTLS"
        result = LinkParser.parse_link(link)
        tls = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert tls["alpn"] == ["h2", "http/1.1"]
        assert tls["fingerprint"] == "chrome"
        assert tls["allowInsecure"] is True

    def test_parse_vless_h3_quic(self):
        """Test VLESS with H3/QUIC transport."""
        link = "vless://uuid@host:443?type=h3&quicSecurity=aes-128-gcm&key=mykey&headerType=srtp#H3Server"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "quic"
        assert ss["quicSettings"]["security"] == "aes-128-gcm"
        assert ss["quicSettings"]["key"] == "mykey"
        assert ss["quicSettings"]["type"] == "srtp"

    def test_parse_vless_httpupgrade(self):
        """Test VLESS with HTTPUpgrade transport."""
        link = "vless://uuid@host:443?type=httpupgrade&path=/up&host=uphost#UpgradeServer"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "httpupgrade"
        assert ss["httpupgradeSettings"]["path"] == "/up"
        assert ss["httpupgradeSettings"]["host"] == "uphost"

    def test_parse_vless_splithttp_full(self):
        """Test splithttp with scMax parameters."""
        link = "vless://uuid@host:443?type=splithttp&scMaxEachPostBytes=1000000&scMaxConcurrentPosts=5"
        result = LinkParser.parse_link(link)
        # Link parser normalizes splithttp to xhttp and uses xhttpSettings
        ss = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]
        assert ss["scMaxEachPostBytes"] == 1000000
        assert ss["scMaxConcurrentPosts"] == 5

    def test_parse_hysteria2_obfs(self):
        """Test Hysteria2 with OBFS."""
        link = "hysteria2://pass@host:443?obfs=salamander&obfs-password=obfspass#HysObfs"
        result = LinkParser.parse_link(link)
        obfs = result["config"]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["obfs"]
        assert obfs["type"] == "salamander"
        assert obfs["password"] == "obfspass"

    def test_parse_vmess_kcp(self):
        """Test VMess with KCP and header type."""
        vmess_data = {
            "v": "2",
            "ps": "KCP",
            "add": "kcp.com",
            "port": 123,
            "id": "uuid",
            "net": "kcp",
            "type": "wechat-video",
        }
        link = f"vmess://{base64.b64encode(json.dumps(vmess_data).encode()).decode()}"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "kcp"
        assert ss["kcpSettings"]["header"]["type"] == "wechat-video"

    def test_parse_vmess_grpc(self):
        """Test VMess with gRPC (path mapped to serviceName)."""
        vmess_data = {
            "v": "2",
            "ps": "gRPC",
            "add": "grpc.com",
            "port": 443,
            "id": "uuid",
            "net": "grpc",
            "path": "myserv",
        }
        link = f"vmess://{base64.b64encode(json.dumps(vmess_data).encode()).decode()}"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "grpc"
        assert ss["grpcSettings"]["serviceName"] == "myserv"

    def test_parse_trojan_grpc(self):
        """Test Trojan with gRPC."""
        link = "trojan://pass@host:443?type=grpc&serviceName=tjserv#TrojangRPC"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "grpc"
        assert ss["grpcSettings"]["serviceName"] == "tjserv"

    def test_generate_vmess(self):
        """Test generating VMess link."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vmess",
                    "settings": {
                        "vnext": [
                            {
                                "address": "vm.com",
                                "port": 443,
                                "users": [{"id": "id", "alterId": 0}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "ws",
                        "wsSettings": {"path": "/v", "headers": {"Host": "vhost"}},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "VGen")
        assert "vmess://" in link
        decoded = json.loads(base64.b64decode(link[8:]).decode())
        assert decoded["ps"] == "VGen"
        assert decoded["add"] == "vm.com"
        assert decoded["net"] == "ws"
        assert decoded["path"] == "/v"

    def test_generate_trojan(self):
        """Test generating Trojan link."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "tj.com", "port": 443, "password": "pass"}]},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "tls",
                        "tlsSettings": {"serverName": "tj.sni"},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "TGen")
        assert "trojan://pass@tj.com:443" in link
        assert "sni=tj.sni" in link

    def test_generate_hysteria2(self):
        """Test generating Hysteria2 link."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "hysteria2",
                    "settings": {
                        "vnext": [
                            {
                                "address": "hy.com",
                                "port": 443,
                                "users": [{"password": "pass"}],
                            }
                        ]
                    },
                    "streamSettings": {"tlsSettings": {"serverName": "hy.sni", "allowInsecure": True}},
                }
            ]
        }
        link = LinkParser.generate_link(config, "HGen")
        assert "hysteria2://pass@hy.com:443" in link
        assert "sni=hy.sni" in link
        assert "insecure=1" in link

    def test_generate_vless_full(self):
        """Test VLESS generator with all optional features for coverage."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": "a.com",
                                "port": 443,
                                "users": [{"id": "id", "encryption": "aes-128-gcm"}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "ws",
                        "security": "tls",
                        "tlsSettings": {
                            "serverName": "sni",
                            "alpn": ["h2"],
                            "fingerprint": "chrome",
                        },
                        "wsSettings": {"path": "/ws", "headers": {"Host": "vhost"}},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "FullVGen")
        assert "encryption=aes-128-gcm" in link
        assert "alpn=h2" in link
        assert "fp=chrome" in link
        assert "host=vhost" in link

    def test_parse_vmess_tls_details_full(self):
        """Test VMess with complex TLS and ALPN."""
        vmess_data = {
            "v": "2",
            "ps": "V",
            "add": "v.com",
            "port": 443,
            "id": "uuid",
            "tls": "tls",
            "sni": "vsni",
            "alpn": "h2",
            "fp": "chrome",
        }
        link = f"vmess://{base64.b64encode(json.dumps(vmess_data).encode()).decode()}"
        res = LinkParser.parse_link(link)
        tls = res["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert tls["serverName"] == "vsni"
        assert tls["alpn"] == ["h2"]
        assert tls["fingerprint"] == "chrome"

    def test_generate_vmess_full(self):
        """Test VMess generator with TLS and ALPN."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vmess",
                    "settings": {
                        "vnext": [
                            {
                                "address": "v.com",
                                "port": 443,
                                "users": [{"id": "id", "alterId": 0}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "tls",
                        "tlsSettings": {"serverName": "vsni", "alpn": ["h2"]},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "VFull")
        decoded = json.loads(base64.b64decode(link[8:]).decode())
        assert decoded["tls"] == "tls"
        assert decoded["sni"] == "vsni"
        assert decoded["alpn"] == "h2"

    def test_generate_unsupported_cases(self):
        """Test generating link for unsupported protocol."""
        config = {"outbounds": [{"tag": "proxy", "protocol": "unknown"}]}
        assert LinkParser.generate_link(config, "test") == ""
        assert LinkParser.generate_link({}, "test") == ""
        # Exception case
        assert LinkParser.generate_link(None, "test") == ""

    def test_parse_vless_full_transport_suite(self):
        """Test VLESS with all common transport types."""
        # WS
        link_ws = "vless://uuid@host:443?type=ws&path=/ws&host=wshost#WS"
        res_ws = LinkParser.parse_link(link_ws)
        assert res_ws["config"]["outbounds"][0]["streamSettings"]["network"] == "ws"

        # gRPC
        link_grpc = "vless://uuid@host:443?type=grpc&serviceName=grpcserv#gRPC"
        res_grpc = LinkParser.parse_link(link_grpc)
        assert res_grpc["config"]["outbounds"][0]["streamSettings"]["network"] == "grpc"

        # HTTP
        link_http = "vless://uuid@host:443?type=http&path=/h&host=hhost#HTTP"
        res_http = LinkParser.parse_link(link_http)
        assert res_http["config"]["outbounds"][0]["streamSettings"]["network"] == "http"

    def test_parse_vless_reality_full(self):
        """Test VLESS Reality with all parameters."""
        link = "vless://uuid@host:443?security=reality&pbk=pub&sid=s1,s2&fp=chrome&sni=target.com#Reality"
        res = LinkParser.parse_link(link)
        rs = res["config"]["outbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["publicKey"] == "pub"
        assert rs["shortIds"] == ["s1", "s2"]
        assert rs["fingerprint"] == "chrome"
        assert rs["serverName"] == "target.com"

    def test_parse_vmess_http_quic(self):
        """Test VMess with H2(HTTP) and QUIC transports."""
        # H2
        data_h2 = {
            "v": "2",
            "add": "h2.com",
            "net": "h2",
            "path": "/path",
            "host": "h1,h2",
        }
        link_h2 = f"vmess://{base64.b64encode(json.dumps(data_h2).encode()).decode()}"
        res_h2 = LinkParser.parse_link(link_h2)
        assert res_h2["config"]["outbounds"][0]["streamSettings"]["network"] == "http"

        # QUIC
        data_quic = {
            "v": "2",
            "add": "q.com",
            "net": "quic",
            "type": "srtp",
            "host": "aes-128-gcm",
        }
        link_quic = f"vmess://{base64.b64encode(json.dumps(data_quic).encode()).decode()}"
        res_quic = LinkParser.parse_link(link_quic)
        qs = res_quic["config"]["outbounds"][0]["streamSettings"]["quicSettings"]
        assert qs["security"] == "aes-128-gcm"
        assert qs["header"]["type"] == "srtp"

    def test_generate_vless_complex(self):
        """Test VLESS generator with Reality and gRPC."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": "r.com",
                                "port": 443,
                                "users": [{"id": "id", "flow": "xtls-rprx-vision"}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "grpc",
                        "security": "reality",
                        "realitySettings": {
                            "serverName": "sni",
                            "publicKey": "pub",
                            "shortIds": ["sid"],
                            "fingerprint": "chrome",
                        },
                        "grpcSettings": {"serviceName": "serv"},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "RGen")
        assert "vless://" in link
        assert "security=reality" in link
        assert "flow=xtls-rprx-vision" in link
        assert "serviceName=serv" in link

    def test_generate_vmess_grpc(self):
        """Test VMess generator with gRPC."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vmess",
                    "settings": {"vnext": [{"address": "g.com", "port": 443, "users": [{"id": "id"}]}]},
                    "streamSettings": {
                        "network": "grpc",
                        "grpcSettings": {"serviceName": "serv"},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "GGen")
        decoded = json.loads(base64.b64decode(link[8:]).decode())
        assert decoded["net"] == "grpc"
        assert decoded["path"] == "serv"

    def test_generate_trojan_ws(self):
        """Test Trojan generator with WebSocket."""
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "w.com", "port": 443, "password": "p"}]},
                    "streamSettings": {
                        "network": "ws",
                        "wsSettings": {"path": "/ws", "headers": {"Host": "whost"}},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(config, "WGen")
        assert "trojan://p@w.com:443" in link
        assert "type=ws" in link
        assert "path=/ws" in link
        assert "host=whost" in link

    def test_parse_vless_error_cases(self):
        """Additional VLESS error cases for coverage."""
        with pytest.raises(ValueError, match="missing address"):
            LinkParser.parse_link("vless://uuid@:443")
        with pytest.raises(ValueError, match="missing address"):
            # addr will be empty here if we use vless://uuid@?params
            LinkParser.parse_link("vless://uuid@?type=tcp")
        with pytest.raises(ValueError, match="Invalid port"):
            LinkParser.parse_link("vless://uuid@host:70000")

    def test_parse_vless_splithttp_errors(self):
        """Test error handling in splithttp parameters."""
        link = "vless://uuid@host:443?type=splithttp&scMaxEachPostBytes=abc&scMaxConcurrentPosts=-1"
        res = LinkParser.parse_link(link)
        # Link parser normalizes splithttp to xhttp and uses xhttpSettings
        ss = res["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]
        assert "scMaxEachPostBytes" not in ss
        assert "scMaxConcurrentPosts" not in ss
