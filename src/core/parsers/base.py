"""Base parsing utilities, type casters, and shared constants."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from loguru import logger

from src.core.constants import VALID_FINGERPRINTS, XHTTP_EXTRA_KEYS

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

# Dynamic Mapping Router type system
BOOL_TRUE = {"true", "1", "yes"}
BOOL_FALSE = {"false", "0", "no"}

# Comma-separated fields that should be split into lists
SPLIT_FIELDS = {
    "alpn",
    "sid",
    "fm_tcp_lengths",
    "fm_tcp_delays",
    "fm_udp_rand",
    "fm_udp_delay",
}

# XHTTP/SplitHTTP param keys that route into xhttpSettings
XHTTP_PARAMS = {
    "mode",
    "noSSEHeader",
    "downloadProxy",
    "uplinkHTTPMethod",
    "downlinkHTTPMethod",
    "xPaddingBytes",
    "scMaxEachGetBytes",
    "scMaxEachPostBytes",
    "scMinPostsIntervalMs",
    "scStreamUpServerSecs",
    "scMaxBufferedPosts",
    "scMaxConcurrentPosts",
    "xmuxMaxConcurrency",
    "xmuxMaxConnections",
    "xmuxCMaxReuseTimes",
    "xmuxHMaxReusableSecs",
    "xmuxHMaxRequestTimes",
}

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
    "download_proxy": "downloadProxy",
    "uplink_http_method": "uplinkHTTPMethod",
    "downlink_http_method": "downlinkHTTPMethod",
    "sc_max_each_get_bytes": "scMaxEachGetBytes",
    "sc_min_posts_interval_ms": "scMinPostsIntervalMs",
}


def _to_camel(suffix: str) -> str:
    """Convert underscore_separated suffix to camelCase, with known overrides."""
    if suffix in SUFFIX_CAMEL_MAP:
        return SUFFIX_CAMEL_MAP[suffix]
    parts = suffix.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _get_cipher_suites(get_param) -> str:
    """Read cipherSuites from 'cs' or 'cipherSuites' query param (cs takes precedence)."""
    cs = get_param("cs")
    if cs:
        return cs
    return get_param("cipherSuites") or ""


def _validate_fingerprint(fp: str) -> str:
    """Warn if fingerprint is not in the known set; still pass it through."""
    if fp and fp not in VALID_FINGERPRINTS:
        logger.warning(f"Unknown fingerprint: {fp} (valid: {sorted(VALID_FINGERPRINTS)})")
    return fp


def _nest_xhttp_extra(xhttp: dict) -> dict:
    """Move fields that belong in the 'extra' dict out of the root level."""
    extra = xhttp.pop("extra", None)
    if not isinstance(extra, dict):
        extra = {}
    for key in list(xhttp.keys()):
        if key in XHTTP_EXTRA_KEYS:
            extra[key] = xhttp.pop(key)
    if extra:
        xhttp["extra"] = extra
    return xhttp


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
    """Route fm_* query params into the finalmask nested structure."""
    finalmask: Dict[str, Any] = {}

    tcp_group: Dict[str, Any] = {}
    udp_group: Dict[str, Any] = {}
    quic_group: Dict[str, Any] = {}

    for key, raw in raw_params.items():
        if key == "fm_tcp_type":
            tcp_group["type"] = raw
        elif key.startswith("fm_tcp_"):
            suffix = _to_camel(key[7:])
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
    """Dynamically collect XHTTP/SplitHTTP parameters into xhttpSettings block."""
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


def build_minimal_config(outbound: Dict) -> Dict:
    """Helper to wrap outbound in minimal config structure."""
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
                {"type": "field", "outboundTag": "direct", "domain": ["geosite:private"]},
                {"type": "field", "outboundTag": "block", "domain": ["geosite:category-ads-all"]},
            ],
        },
    }
