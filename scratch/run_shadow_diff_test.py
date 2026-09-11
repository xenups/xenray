"""Run shadow-test diff comparison between LibXrayParserAdapter and Python parsers."""

import json
from loguru import logger
from src.core.parsers.binary_parser_adapter import LibXrayParserAdapter
from src.core.parsers.vless import VlessParser
from src.core.parsers.vmess import VmessParser

links = [
    # 1. VLESS TLS WS
    (
        "VLESS TLS WS",
        "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&sni=example.com&type=ws&path=%2Fws#SampleTLS",
        VlessParser.parse,
    ),
    # 2. VLESS Reality Vision
    (
        "VLESS Reality Vision",
        "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=reality&sni=example.com&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=0123456789abcdef&flow=xtls-rprx-vision&fp=chrome#SampleReality",
        VlessParser.parse,
    ),
    # 3. VLESS ECH
    (
        "VLESS ECH",
        "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&sni=example.com&type=ws&path=%2Fws&ech=AEX%2BAA==&fp=chrome#SampleECH",
        VlessParser.parse,
    ),
    # 4. VLESS FinalMask
    (
        "VLESS FinalMask",
        "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&sni=example.com&type=tcp&headerType=none&fm=%7B%22tcp%22%3A%5B%7B%22type%22%3A%22http%22%7D%5D%7D#SampleFM",
        VlessParser.parse,
    ),
    # 5. VLESS XHTTP
    (
        "VLESS XHTTP",
        "vless://00000000-0000-0000-0000-000000000001@example.com:443?type=xhttp&path=%2Fxhttp&mode=auto&security=tls&sni=example.com&extra=%7B%22noSSEHeader%22%3Atrue%7D#SampleXHTTP",
        VlessParser.parse,
    ),
    # 6. VMess WS TLS
    (
        "VMess WS TLS",
        "vmess://eyJ2IjoiMiIsInBzIjoiVk1lc3NTYW1wbGUiLCJhZGQiOiJ2bWVzcy5leGFtcGxlLmNvbSIsInBvcnQiOiI0NDMiLCJpZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMiIsImFpZCI6IjAiLCJzY3kiOiJhdXRvIiwibmV0Ijoid3MiLCJ0eXBlIjoibm9uZSIsImhvc3QiOiJ2bWVzcy5leGFtcGxlLmNvbSIsInBhdGgiOiIvdm1lc3MiLCJ0bHMiOiJ0bHMiLCJzbmkiOiJ2bWVzcy5leGFtcGxlLmNvbSJ9",
        VmessParser.parse,
    ),
]

print("=" * 80)
print("SHADOW-TEST DIFF EXECUTION (libXray vs Python Parser)")
print("=" * 80)

for label, link, fallback_fn in links:
    print(f"\n--- [Test Case] {label} ---")
    print(f"Link: {link[:75]}...")
    
    # Run Python parser
    try:
        py_res = fallback_fn(link)
        py_out = py_res.get("config", {}).get("outbounds", [{}])[0]
        py_status = "OK"
    except Exception as e:
        py_status = f"FAIL: {e}"
        py_out = {}

    # Run libXray binary parser
    try:
        go_res = LibXrayParserAdapter.parse(link)
        go_out = go_res.get("config", {}).get("outbounds", [{}])[0]
        go_status = "OK"
    except Exception as e:
        go_status = f"FAIL: {e}"
        go_out = {}

    print(f"Status -> Python: {py_status} | libXray Go: {go_status}")

    # Detailed diff comparison
    diffs = []
    
    # 1. Protocol
    if py_out.get("protocol") != go_out.get("protocol"):
        diffs.append(f"protocol: python={py_out.get('protocol')} vs libxray={go_out.get('protocol')}")

    # 2. Network & Security
    p_stream = py_out.get("streamSettings", {})
    g_stream = go_out.get("streamSettings", {})
    if p_stream.get("network") != g_stream.get("network"):
        diffs.append(f"stream.network: python={p_stream.get('network')} vs libxray={g_stream.get('network')}")
    if p_stream.get("security") != g_stream.get("security"):
        diffs.append(f"stream.security: python={p_stream.get('security')} vs libxray={g_stream.get('security')}")

    # 3. Security Settings (TLS / Reality / ECH)
    for sec_key in ("tlsSettings", "realitySettings"):
        p_sec = p_stream.get(sec_key, {})
        g_sec = g_stream.get(sec_key, {})
        for k in set(list(p_sec.keys()) + list(g_sec.keys())):
            pv = p_sec.get(k)
            gv = g_sec.get(k)
            if pv != gv:
                diffs.append(f"{sec_key}.{k}: python={pv} vs libxray={gv}")

    # 4. Transport settings (wsSettings, xhttpSettings, finalmask)
    for t_key in ("wsSettings", "xhttpSettings", "finalmask"):
        p_t = p_stream.get(t_key)
        g_t = g_stream.get(t_key)
        if p_t != g_t:
            diffs.append(f"{t_key}: python={json.dumps(p_t)} vs libxray={json.dumps(g_t)}")

    if diffs:
        print("Discrepancies found:")
        for d in diffs:
            print(f"  * {d}")
    else:
        print("  -> Identical structure!")
