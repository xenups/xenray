"""Download sing-box rule-sets (.srs) into assets/rules/ with mirror fallback.

Mirrors tried per file: jsDelivr CDN -> raw.githubusercontent.com -> GitHub release proxy.
Only non-empty downloads pass the size check; existing files are overwritten only
on success (atomic tmp+rename), so a failed network never leaves a partial file.
"""

from __future__ import annotations

import os
import sys

import requests

TARGET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "rules")

FILES = [
    # (target filename, [mirror urls])
    (
        "geoip-ir.srs",
        [
            "https://cdn.jsdelivr.net/gh/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs",
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs",
        ],
    ),
    (
        "geosite-ir.srs",
        [
            "https://cdn.jsdelivr.net/gh/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs",
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs",
        ],
    ),
    (
        "geosite-category-ads-all.srs",
        [
            "https://cdn.jsdelivr.net/gh/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-category-ads-all.srs",
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-category-ads-all.srs",
            "https://cdn.jsdelivr.net/gh/SagerNet/sing-geosite/rule-set/geosite-category-ads-all.srs",
        ],
    ),
    (
        "geoip-cn.srs",
        [
            "https://cdn.jsdelivr.net/gh/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
            "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
        ],
    ),
    (
        "ru-bundle.srs",
        [
            "https://cdn.jsdelivr.net/gh/legiz-ru/sb-rule-sets@main/ru-bundle.srs",
            "https://github.com/legiz-ru/sb-rule-sets/raw/main/ru-bundle.srs",
        ],
    ),
]

MIN_SIZE = 1024  # a sane .srs is at least 1KB (ads-all ~350KB)


def _fetch(url: str, timeout: int = 25) -> bytes | None:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "xenray-build"})
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception as exc:
        print(f"    mirror failed ({type(exc).__name__}): {url}")
    return None


def main() -> int:
    os.makedirs(TARGET_DIR, exist_ok=True)
    ok, failed = 0, 0
    for name, mirrors in FILES:
        print(f"[{name}]")
        data = None
        for url in mirrors:
            data = _fetch(url)
            if data is not None:
                print(f"  fetched {len(data)} bytes from {url}")
                break
        if data is None or len(data) < MIN_SIZE:
            print(f"  FAILED: no mirror delivered >= {MIN_SIZE} bytes")
            failed += 1
            continue
        tmp = os.path.join(TARGET_DIR, name + ".tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, os.path.join(TARGET_DIR, name))
        print(f"  saved -> {os.path.join(TARGET_DIR, name)}")
        ok += 1
    print(f"\nDONE: {ok} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
