"""Download sing-box rule-sets (.srs) into assets/rules/ with mirror fallback.

Mirrors tried per file: raw.githubusercontent.com -> jsDelivr CDN -> GitHub repo.
Only non-empty downloads pass the size check; existing files are overwritten only
on success (atomic tmp+rename), so a failed network never leaves a partial file.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

DEFAULT_TARGET_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "rules"))

FILES = [
    # (target filename, [mirror urls])
    (
        "geoip-ir.srs",
        [
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs",
            "https://cdn.jsdelivr.net/gh/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs",
        ],
    ),
    (
        "geosite-ir.srs",
        [
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs",
            "https://cdn.jsdelivr.net/gh/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs",
        ],
    ),
    (
        "geosite-category-ads-all.srs",
        [
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-category-ads-all.srs",
            "https://cdn.jsdelivr.net/gh/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-category-ads-all.srs",
            "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-category-ads-all.srs",
            "https://cdn.jsdelivr.net/gh/SagerNet/sing-geosite/rule-set/geosite-category-ads-all.srs",
        ],
    ),
    (
        "geoip-cn.srs",
        [
            "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
            "https://cdn.jsdelivr.net/gh/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
        ],
    ),
    (
        "ru-bundle.srs",
        [
            "https://raw.githubusercontent.com/legiz-ru/sb-rule-sets/main/ru-bundle.srs",
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


def download_rule_sets(
    target_dir: str = DEFAULT_TARGET_DIR,
    force: bool = True,
    timeout: int = 25,
) -> int:
    """Download sing-box rule sets into target directory."""
    os.makedirs(target_dir, exist_ok=True)
    ok, failed = 0, 0
    for name, mirrors in FILES:
        print(f"[{name}]")
        final_path = os.path.join(target_dir, name)
        if not force and os.path.exists(final_path) and os.path.getsize(final_path) >= MIN_SIZE:
            print(f"  [SKIP] {name} already exists (use --force to overwrite)")
            ok += 1
            continue

        data = None
        for url in mirrors:
            data = _fetch(url, timeout=timeout)
            if data is not None and len(data) >= MIN_SIZE:
                print(f"  fetched {len(data)} bytes from {url}")
                break

        if data is None or len(data) < MIN_SIZE:
            print(f"  FAILED: no mirror delivered >= {MIN_SIZE} bytes")
            failed += 1
            continue

        tmp = os.path.join(target_dir, name + ".tmp")
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, final_path)
            print(f"  saved -> {final_path}")
            ok += 1
        except Exception as e:
            if os.path.exists(tmp):
                os.unlink(tmp)
            print(f"  FAILED saving {name}: {e}")
            failed += 1

    print(f"\nDONE: {ok} ok, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download sing-box rule sets (.srs)")
    parser.add_argument(
        "--dest",
        default=DEFAULT_TARGET_DIR,
        help="Destination directory (default: assets/rules)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=True,
        help="Force overwrite existing rule sets (default: True)",
    )
    parser.add_argument(
        "--no-force",
        dest="force",
        action="store_false",
        help="Skip existing rule sets",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Timeout per request in seconds (default: 25)",
    )
    args = parser.parse_args()

    return download_rule_sets(
        target_dir=args.dest,
        force=args.force,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
