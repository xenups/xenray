"""Comprehensive tests for LinkParser — Dynamic Mapping Router, all protocols, FinalMask, ECH."""
import base64
import json
import urllib.parse

import pytest

from src.utils.link_parser import (
    LinkParser,
    _cast_value,
    _expand_fm_to_params,
    _maybe_split,
    _route_fm_params,
    _route_xhttp_params,
    _to_camel,
)

# ===================================================================
# Dynamic Mapping Router — unit tests
# ===================================================================


class TestTypeCasting:
    def test_cast_true_variants(self):
        for v in ("true", "True", "TRUE", "1", "yes"):
            assert _cast_value(v) is True, f"failed for {v!r}"

    def test_cast_false_variants(self):
        for v in ("false", "False", "FALSE", "0", "no"):
            assert _cast_value(v) is False, f"failed for {v!r}"

    def test_cast_int(self):
        assert _cast_value("42") == 42
        assert isinstance(_cast_value("42"), int)
        assert _cast_value("0") is False  # 0 is falsy — edge case already handled

    def test_cast_float(self):
        assert _cast_value("3.14") == 3.14
        assert isinstance(_cast_value("3.14"), float)

    def test_cast_float_whole(self):
        assert _cast_value("2.0") == 2
        assert isinstance(_cast_value("2.0"), int)

    def test_cast_str_fallback(self):
        assert _cast_value("hello") == "hello"
        assert _cast_value("60 mbps") == "60 mbps"
        assert _cast_value("3-5") == "3-5"  # range strings stay as str


class TestStringSplitting:
    def test_split_alpn(self):
        assert _maybe_split("alpn", "h2,http/1.1") == ["h2", "http/1.1"]

    def test_split_sid(self):
        assert _maybe_split("sid", "s1,s2,s3") == ["s1", "s2", "s3"]

    def test_non_splittable_key(self):
        assert _maybe_split("host", "example.com") == "example.com"
        assert _maybe_split("path", "/ws") == "/ws"

    def test_split_fm_lengths(self):
        assert _maybe_split("fm_tcp_lengths", "3-5,6-8,10-20") == ["3-5", "6-8", "10-20"]

    def test_split_empty_part(self):
        assert _maybe_split("alpn", "h2,,http/1.1") == ["h2", "http/1.1"]


class TestCamelCase:
    def test_known_mappings(self):
        assert _to_camel("brutal_up") == "brutalUp"
        assert _to_camel("brutal_down") == "brutalDown"
        assert _to_camel("max_split") == "maxSplit"
        assert _to_camel("packet_size") == "packetSize"

    def test_unknown_suffix(self):
        assert _to_camel("hello_world") == "helloWorld"
        assert _to_camel("test") == "test"

    def test_single_word(self):
        assert _to_camel("reset") == "reset"


class TestFinalMaskRouting:
    def test_tcp_fragment(self):
        fm = _route_fm_params(
            {
                "fm_tcp_type": "fragment",
                "fm_tcp_lengths": "3-5,6-8",
                "fm_tcp_delays": "10-20",
                "fm_tcp_max_split": "3-6",
            }
        )
        assert "tcp" in fm
        assert len(fm["tcp"]) == 1
        m = fm["tcp"][0]
        assert m["type"] == "fragment"
        # Comma-separated → list; single value → string
        assert m["settings"]["lengths"] == ["3-5", "6-8"]
        assert m["settings"]["delays"] == "10-20"
        assert m["settings"]["maxSplit"] == "3-6"

    def test_tcp_sudoku(self):
        fm = _route_fm_params(
            {
                "fm_tcp_type": "sudoku",
                "fm_tcp_sudoku_pwd": "secret",
                "fm_tcp_sudoku_ascii": "abc",
            }
        )
        assert fm["tcp"][0]["type"] == "sudoku"
        # fm_tcp_sudoku_pwd maps via SUFFIX_CAMEL to "password"
        assert fm["tcp"][0]["settings"]["password"] == "secret"
        assert fm["tcp"][0]["settings"]["ascii"] == "abc"

    def test_udp_noise(self):
        fm = _route_fm_params(
            {
                "fm_udp_type": "noise",
                "fm_udp_reset": "30-60",
                "fm_udp_rand": "1-8192",
            }
        )
        assert "udp" in fm
        m = fm["udp"][0]
        assert m["type"] == "noise"
        assert m["settings"]["reset"] == "30-60"
        # Single value → string, not list
        assert m["settings"]["rand"] == "1-8192"

    def test_udp_salamander(self):
        fm = _route_fm_params(
            {
                "fm_udp_type": "salamander",
                "fm_udp_salamander_pwd": "obfpass",
                "fm_udp_packet_size": "512-1200",
            }
        )
        m = fm["udp"][0]
        assert m["type"] == "salamander"
        assert m["settings"]["password"] == "obfpass"
        assert m["settings"]["packetSize"] == "512-1200"

    def test_udp_header_custom(self):
        fm = _route_fm_params({"fm_udp_type": "header-custom"})
        assert fm["udp"][0]["type"] == "header-custom"

    def test_quic_params(self):
        fm = _route_fm_params(
            {
                "fm_quic_congestion": "force-brutal",
                "fm_quic_brutal_up": "60 mbps",
                "fm_quic_brutal_down": "0",
            }
        )
        qp = fm["quicParams"]
        assert qp["congestion"] == "force-brutal"
        assert qp["brutalUp"] == "60 mbps"
        # FinalMask values are raw strings (no type casting)
        assert qp["brutalDown"] == "0"

    def test_no_fm_params(self):
        assert _route_fm_params({}) == {}
        assert _route_fm_params({"type": "tcp"}) == {}

    def test_type_only_no_settings(self):
        fm = _route_fm_params({"fm_tcp_type": "fragment"})
        assert fm["tcp"][0]["type"] == "fragment"
        assert "settings" not in fm["tcp"][0]

    def test_expand_round_trip(self):
        # Use a finalmask with only multi-value lists (single values remain strings)
        fm = {
            "tcp": [{"type": "fragment", "settings": {"lengths": ["3-5", "6-8"], "maxSplit": "3-6"}}],
            "udp": [{"type": "noise", "settings": {"reset": "30-60", "rand": "1-8192"}}],
            "quicParams": {"congestion": "force-brutal", "brutalUp": "60 mbps"},
        }
        params = _expand_fm_to_params(fm)
        param_dict = {}
        for p in params:
            k, _, v = p.partition("=")
            param_dict[k] = v
        fm2 = _route_fm_params(param_dict)
        assert fm2 == fm


class TestXHTTPRouting:
    def test_basic_params(self):
        xh = _route_xhttp_params(
            {
                "mode": "packet-up",
                "noSSEHeader": "true",
                "xPaddingBytes": "100",
            }
        )
        assert xh["mode"] == "packet-up"
        assert xh["noSSEHeader"] is True
        assert xh["xPaddingBytes"] == 100

    def test_xmux_routing(self):
        xh = _route_xhttp_params(
            {
                "xmuxMaxConcurrency": "16",
                "xmuxHMaxReusableSecs": "1800",
                "xmuxCMaxReuseTimes": "3",
            }
        )
        assert xh["xmux"]["maxConcurrency"] == 16
        assert xh["xmux"]["hMaxReusableSecs"] == 1800
        assert xh["xmux"]["cMaxReuseTimes"] == 3

    def test_sc_params(self):
        xh = _route_xhttp_params(
            {
                "scMaxBufferedPosts": "10",
                "scMaxEachPostBytes": "1000000",
                "scMaxConcurrentPosts": "5",
            }
        )
        assert xh["scMaxBufferedPosts"] == 10
        assert xh["scMaxEachPostBytes"] == 1000000
        assert xh["scMaxConcurrentPosts"] == 5

    def test_empty(self):
        assert _route_xhttp_params({}) == {}
        assert _route_xhttp_params({"type": "tcp"}) == {}


# ===================================================================
# VLESS parser — comprehensive
# ===================================================================


class TestParseVLESS:
    def test_basic_tcp(self):
        result = LinkParser.parse_vless("vless://uuid@example.com:443#Basic")
        ob = result["config"]["outbounds"][0]
        assert result["name"] == "Basic"
        assert ob["protocol"] == "vless"
        assert ob["settings"]["vnext"][0]["address"] == "example.com"
        assert ob["settings"]["vnext"][0]["port"] == 443

    def test_tcp_no_port_default(self):
        result = LinkParser.parse_vless("vless://uuid@example.com")
        port = result["config"]["outbounds"][0]["settings"]["vnext"][0]["port"]
        assert port == 443

    def test_ipv6(self):
        link = "vless://uuid@[2001:db8::1]:8443?type=tcp#IPv6"
        result = LinkParser.parse_link(link)
        addr = result["config"]["outbounds"][0]["settings"]["vnext"][0]["address"]
        assert addr == "[2001:db8::1]"

    def test_tls_full(self):
        link = "vless://uuid@example.com:443?security=tls&sni=sni.com&fp=chrome&alpn=h2,http/1.1&allowInsecure=1#TLS"
        result = LinkParser.parse_link(link)
        tls = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert tls["serverName"] == "sni.com"
        assert tls["fingerprint"] == "chrome"
        assert tls["alpn"] == ["h2", "http/1.1"]
        assert tls["allowInsecure"] is True

    def test_unknown_security_fallback(self):
        link = "vless://uuid@example.com?security=unknown"
        result = LinkParser.parse_link(link)
        assert result["config"]["outbounds"][0]["streamSettings"]["security"] == "none"

    def test_unknown_network_fallback(self):
        link = "vless://uuid@example.com:443?type=unknown"
        result = LinkParser.parse_link(link)
        assert result["config"]["outbounds"][0]["streamSettings"]["network"] == "tcp"

    def test_ws_with_host(self):
        link = "vless://uuid@example.com:443?type=ws&path=/ws&host=vhost#WS"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "ws"
        assert ss["wsSettings"]["path"] == "/ws"
        assert ss["wsSettings"]["headers"]["Host"] == "vhost"

    def test_ws_host_derived_from_sni(self):
        link = "vless://uuid@cdn.com:443?type=ws&security=tls&sni=real.com"
        result = LinkParser.parse_link(link)
        host = result["config"]["outbounds"][0]["streamSettings"]["wsSettings"]["headers"]["Host"]
        assert host == "real.com"

    def test_ws_host_fallback_address(self):
        link = "vless://uuid@example.com:443?type=ws"
        result = LinkParser.parse_link(link)
        host = result["config"]["outbounds"][0]["streamSettings"]["wsSettings"]["headers"]["Host"]
        assert host == "example.com"

    def test_grpc(self):
        link = "vless://uuid@example.com:443?type=grpc&serviceName=myservice"
        result = LinkParser.parse_link(link)
        grpc = result["config"]["outbounds"][0]["streamSettings"]["grpcSettings"]
        assert grpc["serviceName"] == "myservice"

    def test_http_transport(self):
        link = "vless://uuid@example.com:443?type=http&path=/api&host=hhost"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "http"
        assert ss["httpSettings"]["path"] == "/api"
        assert ss["httpSettings"]["host"] == "hhost"

    def test_httpupgrade(self):
        link = "vless://uuid@example.com:443?type=httpupgrade&path=/up&host=uphost"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "httpupgrade"
        assert ss["httpupgradeSettings"]["path"] == "/up"
        assert ss["httpupgradeSettings"]["host"] == "uphost"

    def test_quic_transport(self):
        link = "vless://uuid@example.com:443?type=quic&quicSecurity=aes-128-gcm&key=mykey&headerType=srtp"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "quic"
        assert ss["quicSettings"]["security"] == "aes-128-gcm"
        assert ss["quicSettings"]["key"] == "mykey"
        assert ss["quicSettings"]["type"] == "srtp"

    def test_h3_normalized_to_quic(self):
        link = "vless://uuid@example.com:443?type=h3"
        result = LinkParser.parse_link(link)
        assert result["config"]["outbounds"][0]["streamSettings"]["network"] == "quic"

    def test_quic_no_key(self):
        link = "vless://uuid@example.com:443?type=quic&quicSecurity=none"
        result = LinkParser.parse_link(link)
        qs = result["config"]["outbounds"][0]["streamSettings"]["quicSettings"]
        assert "key" not in qs

    def test_quic_no_header_type(self):
        link = "vless://uuid@example.com:443?type=quic&quicSecurity=none"
        result = LinkParser.parse_link(link)
        qs = result["config"]["outbounds"][0]["streamSettings"]["quicSettings"]
        assert "type" not in qs

    def test_reality_full(self):
        link = (
            "vless://uuid@example.com:443"
            "?security=reality&pbk=publickey&sid=s1,s2"
            "&fp=chrome&sni=target.com&spx=spider#Real"
        )
        result = LinkParser.parse_link(link)
        rs = result["config"]["outbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["publicKey"] == "publickey"
        assert rs["shortId"] == "s1"
        assert rs["fingerprint"] == "chrome"
        assert rs["serverName"] == "target.com"
        assert rs["spiderX"] == "spider"

    def test_reality_missing_pbk(self):
        with pytest.raises(ValueError, match="pbk"):
            LinkParser.parse_link("vless://uuid@example.com:443?security=reality&sni=target.com")

    def test_reality_missing_sni(self):
        with pytest.raises(ValueError, match="sni"):
            LinkParser.parse_link("vless://uuid@example.com:443?security=reality&pbk=pub")

    @pytest.mark.parametrize(
        "fmt",
        [
            (
                "AF7+DQBaAAAgACA51i3Ssu4wUMV4FNCc8iRX5J+YC4Bhigz9sacl2lCfSQ"
                "AkAAEAAQABAAIAAQADAAIAAQACAAIAAgADAAMAAQADAAIAAwADAAtleGFtcGxlLmNvbQAA"
            ),
            "udp://1.1.1.1",
            "example.com+https://1.1.1.1/dns-query",
        ],
    )
    def test_ech_variants(self, fmt):
        encoded = fmt.replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
        link = f"vless://uuid@example.com:443?security=tls&ech={encoded}#ECH"
        result = LinkParser.parse_link(link)
        ech = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]["echConfigList"]
        assert ech == fmt

    def test_ech_with_sockopt(self):
        sockopt = '{"dialerProxy": "", "tcpFastOpen": true}'
        url_encoded = urllib.parse.quote(sockopt)
        link = f"vless://uuid@example.com:443?security=tls&ech=udp://1.1.1.1&echSockopt={url_encoded}#ECH"
        result = LinkParser.parse_link(link)
        so = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]["echSockopt"]
        assert so["tcpFastOpen"] is True

    def test_invalid_ech_sockopt(self):
        link = "vless://uuid@example.com:443?security=tls&ech=udp://1.1.1.1&echSockopt=not-json"
        result = LinkParser.parse_link(link)
        assert "echSockopt" not in result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]

    def test_tls_no_alpn(self):
        link = "vless://uuid@example.com:443?security=tls&sni=sni.com"
        result = LinkParser.parse_link(link)
        tls = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert "alpn" not in tls

    def test_vless_flow(self):
        link = "vless://uuid@example.com:443?flow=xtls-rprx-vision"
        result = LinkParser.parse_link(link)
        flow = result["config"]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"]
        assert flow == "xtls-rprx-vision"

    def test_encryption(self):
        link = "vless://uuid@example.com:443?encryption=aes-128-gcm"
        result = LinkParser.parse_link(link)
        enc = result["config"]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["encryption"]
        assert enc == "aes-128-gcm"

    def test_vless_error_empty_string(self):
        with pytest.raises(ValueError, match="non-empty"):
            LinkParser.parse_vless("")

    def test_vless_error_not_starting_with_vless(self):
        with pytest.raises(ValueError, match="must start with 'vless://'"):
            LinkParser.parse_vless("ss://abc")

    def test_vless_no_at_sign_uses_placeholder(self):
        # Links without UUID should use zero-UUID placeholder, not raise
        result = LinkParser.parse_link("vless://example.com")
        uuid = result["config"]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"]
        assert uuid == "00000000-0000-0000-0000-000000000000"

    def test_vless_error_empty_address(self):
        with pytest.raises(ValueError, match="missing address"):
            LinkParser.parse_link("vless://uuid@:443#test")

    def test_vless_error_invalid_port(self):
        with pytest.raises(ValueError, match="Invalid port"):
            LinkParser.parse_link("vless://uuid@example.com:99999")


# ===================================================================
# VLESS + FinalMask
# ===================================================================


class TestParseVLESSFinalMask:
    def test_tcp_fragment(self):
        link = (
            "vless://uuid@example.com:443?security=tls"
            "&fm_tcp_type=fragment&fm_tcp_lengths=3-5,6-8"
            "&fm_tcp_delays=10-20&fm_tcp_max_split=3-6#FM"
        )
        result = LinkParser.parse_link(link)
        fm = result["config"]["outbounds"][0]["streamSettings"]["finalmask"]
        m = fm["tcp"][0]
        assert m["type"] == "fragment"
        assert m["settings"]["lengths"] == ["3-5", "6-8"]
        assert m["settings"]["delays"] == "10-20"
        assert m["settings"]["maxSplit"] == "3-6"

    def test_udp_noise(self):
        link = "vless://uuid@example.com:443?fm_udp_type=noise&fm_udp_reset=30-60&fm_udp_rand=1-8192#UDPNoise"
        result = LinkParser.parse_link(link)
        m = result["config"]["outbounds"][0]["streamSettings"]["finalmask"]["udp"][0]
        assert m["type"] == "noise"
        assert m["settings"]["reset"] == "30-60"

    def test_udp_salamander(self):
        link = (
            "vless://uuid@example.com:443"
            "?fm_udp_type=salamander&fm_udp_salamander_pwd=obfpass"
            "&fm_udp_packet_size=512-1200#Salamander"
        )
        result = LinkParser.parse_link(link)
        m = result["config"]["outbounds"][0]["streamSettings"]["finalmask"]["udp"][0]
        assert m["type"] == "salamander"
        assert m["settings"]["password"] == "obfpass"
        assert m["settings"]["packetSize"] == "512-1200"

    def test_quic_brutal(self):
        link = (
            "vless://uuid@example.com:443"
            "?fm_quic_congestion=force-brutal"
            "&fm_quic_brutal_up=60%20mbps"
            "&fm_quic_brutal_down=0#Brutal"
        )
        result = LinkParser.parse_link(link)
        qp = result["config"]["outbounds"][0]["streamSettings"]["finalmask"]["quicParams"]
        assert qp["congestion"] == "force-brutal"
        assert qp["brutalUp"] == "60 mbps"
        # FinalMask values are raw strings (no type casting)
        assert qp["brutalDown"] == "0"

    def test_combined_fm(self):
        link = (
            "vless://uuid@example.com:443?"
            "fm_tcp_type=fragment&fm_tcp_lengths=3-5,6-8"
            "&fm_udp_type=noise&fm_udp_reset=30-60"
            "&fm_quic_congestion=force-brutal"
        )
        result = LinkParser.parse_link(link)
        fm = result["config"]["outbounds"][0]["streamSettings"]["finalmask"]
        assert "tcp" in fm
        assert "udp" in fm
        assert "quicParams" in fm

    def test_round_trip_fm(self):
        link = (
            "vless://uuid@example.com:443?"
            "fm_tcp_type=fragment&fm_tcp_lengths=3-5,6-8&fm_tcp_max_split=3-6"
            "&fm_quic_congestion=force-brutal#RTT"
        )
        r1 = LinkParser.parse_link(link)
        ob1 = r1["config"]["outbounds"][0]
        fm1 = ob1["streamSettings"].get("finalmask", {})

        generated = LinkParser._generate_vless(ob1, "RTT")
        r2 = LinkParser.parse_vless(generated)
        fm2 = r2["config"]["outbounds"][0]["streamSettings"].get("finalmask", {})

        assert fm1 == fm2


# ===================================================================
# XHTTP / SplitHTTP parser
# ===================================================================


class TestParseXHTTP:
    def test_splithttp_normalized_to_xhttp(self):
        link = "vless://uuid@example.com:443?type=splithttp&path=/sp"
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "xhttp"

    def test_xhttp_xmux_params(self):
        link = (
            "vless://uuid@example.com:443?type=splithttp"
            "&mode=packet-up"
            "&noSSEHeader=true"
            "&xPaddingBytes=256"
            "&scMaxBufferedPosts=50"
            "&xmuxMaxConcurrency=16"
            "&xmuxHMaxReusableSecs=1800"
            "#XMUX"
        )
        result = LinkParser.parse_link(link)
        xh = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]
        assert xh["mode"] == "packet-up"
        assert xh["noSSEHeader"] is True
        assert xh["xPaddingBytes"] == 256
        assert xh["scMaxBufferedPosts"] == 50
        assert xh["xmux"]["maxConcurrency"] == 16
        assert xh["xmux"]["hMaxReusableSecs"] == 1800

    def test_xhttp_host_derived_from_sni(self):
        link = "vless://uuid@cdn.com:443?type=splithttp&security=tls&sni=real.com"
        result = LinkParser.parse_link(link)
        host = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]["host"]
        assert host == "real.com"

    def test_xhttp_host_fallback_address(self):
        link = "vless://uuid@example.com:443?type=splithttp"
        result = LinkParser.parse_link(link)
        host = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]["host"]
        assert host == "example.com"

    def test_xhttp_explicit_host(self):
        link = "vless://uuid@cdn.com:443?type=splithttp&security=tls&sni=sni.com&host=custom.com"
        result = LinkParser.parse_link(link)
        host = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]["host"]
        assert host == "custom.com"


# ===================================================================
# Hysteria2
# ===================================================================


class TestParseHysteria2:
    def test_basic(self):
        link = "hysteria2://password@example.com:443#Hys"
        result = LinkParser.parse_link(link)
        ob = result["config"]["outbounds"][0]
        assert ob["protocol"] == "hysteria2"
        assert ob["settings"]["vnext"][0]["users"][0]["password"] == "password"

    def test_with_obfs(self):
        link = "hysteria2://pass@host:443?obfs=salamander&obfs-password=obfpass#Obfs"
        result = LinkParser.parse_link(link)
        obfs = result["config"]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["obfs"]
        assert obfs["type"] == "salamander"
        assert obfs["password"] == "obfpass"

    def test_tls_settings(self):
        link = "hysteria2://pass@host:443?sni=custom.sni&insecure=1"
        result = LinkParser.parse_link(link)
        tls = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert tls["serverName"] == "custom.sni"
        assert tls["allowInsecure"] is True

    def test_sni_fallback_to_address(self):
        link = "hysteria2://pass@example.com:443"
        result = LinkParser.parse_link(link)
        sni = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"]
        assert sni == "example.com"

    def test_error_no_password(self):
        with pytest.raises(ValueError, match="missing password"):
            LinkParser.parse_link("hysteria2://example.com")


# ===================================================================
# VMess
# ===================================================================


class TestParseVMess:
    def _make_link(self, **data):
        d = {"v": "2", "ps": "Test", "add": "example.com", "port": "443", "id": "uuid", **data}
        return f"vmess://{base64.b64encode(json.dumps(d).encode()).decode()}"

    def test_basic(self):
        link = self._make_link()
        result = LinkParser.parse_link(link)
        ob = result["config"]["outbounds"][0]
        assert ob["protocol"] == "vmess"
        assert result["name"] == "Test"

    def test_ws(self):
        link = self._make_link(net="ws", path="/ws", host="vhost")
        result = LinkParser.parse_link(link)
        ws = result["config"]["outbounds"][0]["streamSettings"]["wsSettings"]
        assert ws["path"] == "/ws"
        assert ws["headers"]["Host"] == "vhost"

    def test_tls(self):
        link = self._make_link(tls="tls", sni="sni.com", alpn="h2,http/1.1", fp="chrome")
        result = LinkParser.parse_link(link)
        tls = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert tls["serverName"] == "sni.com"
        assert tls["alpn"] == ["h2", "http/1.1"]
        assert tls["fingerprint"] == "chrome"

    def test_http_transport(self):
        link = self._make_link(net="h2", path="/api", host="h1,h2")
        result = LinkParser.parse_link(link)
        ss = result["config"]["outbounds"][0]["streamSettings"]
        assert ss["network"] == "http"
        hs = ss["httpSettings"]["host"]
        assert hs == ["h1", "h2"]

    def test_quic(self):
        link = self._make_link(net="quic", type="srtp", host="aes-128-gcm")
        result = LinkParser.parse_link(link)
        qs = result["config"]["outbounds"][0]["streamSettings"]["quicSettings"]
        assert qs["security"] == "aes-128-gcm"
        assert qs["header"]["type"] == "srtp"

    def test_kcp(self):
        link = self._make_link(net="kcp", type="wechat-video")
        result = LinkParser.parse_link(link)
        ks = result["config"]["outbounds"][0]["streamSettings"]["kcpSettings"]
        assert ks["header"]["type"] == "wechat-video"

    def test_grpc(self):
        link = self._make_link(net="grpc", path="myservice")
        result = LinkParser.parse_link(link)
        gs = result["config"]["outbounds"][0]["streamSettings"]["grpcSettings"]
        assert gs["serviceName"] == "myservice"

    def test_error_not_vmess(self):
        with pytest.raises(ValueError, match="decode VMess"):
            LinkParser.parse_link("vmess://invalid-base64!!")

    def test_parse_vmess_direct_invalid_start(self):
        with pytest.raises(ValueError, match="Invalid VMess"):
            LinkParser.parse_vmess("ss://somevalue")


# ===================================================================
# Trojan
# ===================================================================


class TestParseTrojan:
    def test_basic(self):
        link = "trojan://password@example.com:443#Troj"
        result = LinkParser.parse_link(link)
        ob = result["config"]["outbounds"][0]
        assert ob["protocol"] == "trojan"
        assert ob["settings"]["servers"][0]["password"] == "password"

    def test_tls(self):
        link = "trojan://pass@example.com:443?sni=custom.sni&allowInsecure=1&fp=chrome&alpn=h2,http/1.1"
        result = LinkParser.parse_link(link)
        tls = result["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
        assert tls["serverName"] == "custom.sni"
        assert tls["allowInsecure"] is True
        assert tls["fingerprint"] == "chrome"
        assert tls["alpn"] == ["h2", "http/1.1"]

    def test_ws(self):
        link = "trojan://pass@example.com:443?type=ws&path=/ws&host=vhost"
        result = LinkParser.parse_link(link)
        ws = result["config"]["outbounds"][0]["streamSettings"]["wsSettings"]
        assert ws["path"] == "/ws"
        assert ws["headers"]["Host"] == "vhost"

    def test_grpc(self):
        link = "trojan://pass@host:443?type=grpc&serviceName=serv"
        result = LinkParser.parse_link(link)
        grpc = result["config"]["outbounds"][0]["streamSettings"]["grpcSettings"]
        assert grpc["serviceName"] == "serv"

    def test_error_not_trojan(self):
        with pytest.raises(ValueError, match="Invalid Trojan"):
            LinkParser.parse_link("trojan://")


# ===================================================================
# Generate link functions
# ===================================================================


class TestGenerateVLESS:
    def _make_outbound(self, **overrides):
        base = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443, "users": [{"id": "uuid"}]}]},
            "streamSettings": {"network": "tcp", "security": "none"},
        }
        base.update(overrides)
        return base

    def test_generate_tcp(self):
        ob = self._make_outbound()
        link = LinkParser._generate_vless(ob, "Gen")
        assert "vless://uuid@example.com:443" in link
        assert "type=tcp" in link

    def test_generate_tls(self):
        ob = self._make_outbound(
            streamSettings={
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {"serverName": "sni.com", "fingerprint": "chrome", "alpn": ["h2"]},
            }
        )
        link = LinkParser._generate_vless(ob, "TLS")
        assert "security=tls" in link
        assert "sni=sni.com" in link
        assert "fp=chrome" in link
        assert "alpn=h2" in link

    def test_generate_reality(self):
        ob = self._make_outbound(
            settings={
                "vnext": [{"address": "r.com", "port": 443, "users": [{"id": "uuid", "flow": "xtls-rprx-vision"}]}]
            },
            streamSettings={
                "network": "grpc",
                "security": "reality",
                "realitySettings": {
                    "serverName": "sni",
                    "publicKey": "pub",
                    "shortId": "sid",
                    "fingerprint": "chrome",
                    "spiderX": "spider",
                },
                "grpcSettings": {"serviceName": "serv"},
            },
        )
        link = LinkParser._generate_vless(ob, "Real")
        assert "security=reality" in link
        assert "flow=xtls-rprx-vision" in link
        assert "serviceName=serv" in link

    def test_generate_ech(self):
        ob = self._make_outbound(
            streamSettings={
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": "sni.com",
                    "echConfigList": "udp://1.1.1.1",
                },
            }
        )
        link = LinkParser._generate_vless(ob, "ECH")
        assert "ech=" in link
        assert "udp" in link

    def test_generate_ech_sockopt(self):
        ob = self._make_outbound(
            streamSettings={
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": "sni.com",
                    "echConfigList": "udp://1.1.1.1",
                    "echSockopt": {"tcpFastOpen": True},
                },
            }
        )
        link = LinkParser._generate_vless(ob, "ECHOpt")
        assert "echSockopt=" in link

    def test_generate_fm_round_trip(self):
        ob = self._make_outbound(
            streamSettings={
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {"serverName": "sni.com"},
                "finalmask": {
                    "tcp": [{"type": "fragment", "settings": {"lengths": ["3-5", "6-8"], "maxSplit": "3-6"}}],
                    "quicParams": {"congestion": "force-brutal"},
                },
            }
        )
        link = LinkParser._generate_vless(ob, "FMGen")
        r2 = LinkParser.parse_vless(link)
        fm2 = r2["config"]["outbounds"][0]["streamSettings"].get("finalmask", {})
        assert fm2["tcp"][0]["type"] == "fragment"
        assert fm2["tcp"][0]["settings"]["lengths"] == ["3-5", "6-8"]
        assert fm2["quicParams"]["congestion"] == "force-brutal"


class TestGenerateVMess:
    def _make_config(self, **stream):
        return {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vmess",
                    "settings": {"vnext": [{"address": "v.com", "port": 443, "users": [{"id": "uuid"}]}]},
                    "streamSettings": {"network": "tcp", **stream},
                }
            ]
        }

    def test_generate_tcp(self):
        link = LinkParser.generate_link(self._make_config(), "VGen")
        assert link.startswith("vmess://")

    def test_generate_tls(self):
        cfg = self._make_config(security="tls", tlsSettings={"serverName": "sni", "alpn": ["h2"]})
        link = LinkParser.generate_link(cfg, "VTLS")
        decoded = json.loads(base64.b64decode(link[8:]).decode())
        assert decoded["tls"] == "tls"
        assert decoded["sni"] == "sni"
        assert decoded["alpn"] == "h2"

    def test_generate_ws(self):
        cfg = self._make_config(network="ws", wsSettings={"path": "/ws", "headers": {"Host": "vhost"}})
        link = LinkParser.generate_link(cfg, "VWS")
        decoded = json.loads(base64.b64decode(link[8:]).decode())
        assert decoded["net"] == "ws"
        assert decoded["path"] == "/ws"
        assert decoded["host"] == "vhost"

    def test_generate_grpc(self):
        cfg = self._make_config(network="grpc", grpcSettings={"serviceName": "serv"})
        link = LinkParser.generate_link(cfg, "VGRPC")
        decoded = json.loads(base64.b64decode(link[8:]).decode())
        assert decoded["net"] == "grpc"
        assert decoded["path"] == "serv"


class TestGenerateTrojan:
    def test_basic(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "tj.com", "port": 443, "password": "pass"}]},
                    "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": {"serverName": "sni"}},
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "TGen")
        assert "trojan://pass@tj.com:443" in link
        assert "sni=sni" in link

    def test_ws(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "w.com", "port": 443, "password": "p"}]},
                    "streamSettings": {
                        "network": "ws",
                        "security": "tls",
                        "tlsSettings": {"serverName": "sni"},
                        "wsSettings": {"path": "/ws", "headers": {"Host": "whost"}},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "TWS")
        assert "type=ws" in link
        assert "path=/ws" in link
        assert "host=whost" in link

    def test_grpc(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "g.com", "port": 443, "password": "p"}]},
                    "streamSettings": {
                        "network": "grpc",
                        "grpcSettings": {"serviceName": "serv"},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "TGRPC")
        assert "serviceName=serv" in link

    def test_no_security(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "tj.com", "port": 443, "password": "pass"}]},
                    "streamSettings": {"network": "tcp"},
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "NoSec")
        assert "security=" not in link


class TestGenerateHysteria2:
    def test_basic(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "hysteria2",
                    "settings": {"vnext": [{"address": "hy.com", "port": 443, "users": [{"password": "pass"}]}]},
                    "streamSettings": {"tlsSettings": {"serverName": "sni", "allowInsecure": True}},
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "HGen")
        assert "hysteria2://pass@hy.com:443" in link
        assert "sni=sni" in link
        assert "insecure=1" in link

    def test_with_obfs(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "hysteria2",
                    "settings": {
                        "vnext": [
                            {
                                "address": "hy.com",
                                "port": 443,
                                "users": [{"password": "pass", "obfs": {"type": "salamander", "password": "obfpass"}}],
                            }
                        ]
                    },
                    "streamSettings": {"tlsSettings": {"serverName": "sni"}},
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "HObfs")
        assert "obfs=salamander" in link


class TestGenerateEdgeCases:
    def test_no_proxy_outbound(self):
        cfg = {"outbounds": [{"tag": "direct", "protocol": "freedom"}]}
        assert LinkParser.generate_link(cfg, "test") == ""

    def test_empty_outbounds(self):
        assert LinkParser.generate_link({"outbounds": []}, "test") == ""

    def test_unsupported_protocol(self):
        cfg = {"outbounds": [{"tag": "proxy", "protocol": "unknown", "settings": {}}]}
        assert LinkParser.generate_link(cfg, "test") == ""

    def test_none_config(self):
        assert LinkParser.generate_link(None, "test") == ""

    def test_vless_reality_ech_config_list(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "a.com", "port": 443, "users": [{"id": "uuid"}]}]},
                    "streamSettings": {
                        "network": "ws",
                        "security": "tls",
                        "tlsSettings": {"serverName": "sni", "echConfigList": "udp://1.1.1.1"},
                        "wsSettings": {"path": "/ws", "headers": {"Host": "vhost"}},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "ECHGen")
        assert "ech=" in link

    def test_vless_ech_config_list(self):
        cfg = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "a.com", "port": 443, "users": [{"id": "uuid"}]}]},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "tls",
                        "tlsSettings": {"serverName": "sni", "echConfig": ["cfg1", "cfg2"]},
                    },
                }
            ]
        }
        link = LinkParser.generate_link(cfg, "ECHList")
        assert "ech=" in link


# ===================================================================
# Round-trip tests: parse → generate → re-parse → identical
# ===================================================================


class TestRoundTrip:
    def _rt(self, link):
        r1 = LinkParser.parse_link(link)
        ob1 = r1["config"]["outbounds"][0]
        generated = LinkParser.generate_link(r1["config"], r1["name"])
        r2 = LinkParser.parse_link(generated)
        ob2 = r2["config"]["outbounds"][0]
        return ob1, ob2, generated

    def test_tcp_tls(self):
        link = (
            "vless://uuid@example.com:443?security=tls&sni=sni.com&fp=chrome&alpn=h2,http/1.1&flow=xtls-rprx-vision#RT"
        )
        _, ob2, gen = self._rt(link)
        assert ob2["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"

    def test_ws(self):
        link = "vless://uuid@example.com:443?type=ws&path=/ws&host=vhost#RTWS"
        _, ob2, gen = self._rt(link)
        assert "type=ws" in gen
        assert "host=vhost" in gen

    def test_grpc(self):
        link = "vless://uuid@example.com:443?type=grpc&serviceName=serv#RTGRPC"
        _, ob2, _ = self._rt(link)
        assert ob2["streamSettings"]["grpcSettings"]["serviceName"] == "serv"

    def test_reality(self):
        link = "vless://uuid@host:443?security=reality&pbk=pub&sid=s1,s2&fp=chrome&sni=target.com#RTReal"
        _, ob2, _ = self._rt(link)
        rs = ob2["streamSettings"]["realitySettings"]
        assert rs["shortId"] == "s1"
        assert rs["publicKey"] == "pub"

    def test_finalmask(self):
        link = (
            "vless://uuid@example.com:443?security=tls&sni=sni.com"
            "&fm_tcp_type=fragment&fm_tcp_lengths=3-5,6-8&fm_tcp_max_split=3-6"
            "&fm_quic_congestion=force-brutal"
            "#RTFM"
        )
        _, ob2, _ = self._rt(link)
        fm2 = ob2["streamSettings"].get("finalmask", {})
        assert fm2["tcp"][0]["type"] == "fragment"
        assert fm2["tcp"][0]["settings"]["lengths"] == ["3-5", "6-8"]
        assert fm2["quicParams"]["congestion"] == "force-brutal"

    def test_trojan(self):
        link = "trojan://pass@host:443?type=ws&path=/ws&host=vhost&sni=sni.com#RTTroj"
        _, ob2, _ = self._rt(link)
        assert ob2["streamSettings"]["wsSettings"]["path"] == "/ws"
        assert ob2["streamSettings"]["tlsSettings"]["serverName"] == "sni.com"

    def test_hysteria2(self):
        link = "hysteria2://pass@host:443?sni=sni.com&insecure=1#RTHys"
        _, ob2, _ = self._rt(link)
        assert ob2["streamSettings"]["tlsSettings"]["serverName"] == "sni.com"
        assert ob2["streamSettings"]["tlsSettings"]["allowInsecure"] is True


# ===================================================================
# Parse link dispatcher
# ===================================================================


class TestParseLink:
    def test_empty_link(self):
        with pytest.raises(ValueError, match="empty"):
            LinkParser.parse_link("")

    def test_unsupported_protocol(self):
        with pytest.raises(ValueError, match="Unsupported"):
            LinkParser.parse_link("ss://base64")

    def test_vless_dispatch(self):
        result = LinkParser.parse_link("vless://uuid@example.com#Dispatch")
        assert result["name"] == "Dispatch"

    def test_vmess_dispatch(self):
        data = {"v": "2", "ps": "VMess", "add": "v.com", "id": "uuid"}
        b64 = base64.b64encode(json.dumps(data).encode()).decode()
        result = LinkParser.parse_link(f"vmess://{b64}")
        assert result["name"] == "VMess"

    def test_trojan_dispatch(self):
        result = LinkParser.parse_link("trojan://pass@host:443#Troj")
        assert result["name"] == "Troj"

    def test_hysteria2_dispatch(self):
        result = LinkParser.parse_link("hysteria2://pass@host#Hys")
        assert result["name"] == "Hys"


# ===================================================================
# Build config
# ===================================================================


class TestBuildConfig:
    def test_structure(self):
        cfg = LinkParser._build_config({"tag": "proxy", "protocol": "vless", "settings": {}})
        assert "log" in cfg
        assert "inbounds" in cfg
        assert len(cfg["outbounds"]) == 3
        assert cfg["outbounds"][1]["protocol"] == "freedom"
        assert cfg["outbounds"][2]["protocol"] == "blackhole"
        assert "routing" in cfg

    def test_routing_rules(self):
        cfg = LinkParser._build_config({"tag": "proxy", "protocol": "vless", "settings": {}})
        rules = cfg["routing"]["rules"]
        assert len(rules) == 3
        assert any(r.get("ip") == ["geoip:private"] for r in rules)
        assert any(r.get("domain") == ["geosite:private"] for r in rules)
