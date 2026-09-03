"""Rule-set materialisation helper — offline-first, rule-sets never crash sing-box.

sing-box FATALs at startup if a ``type: remote`` rule-set download fails
(``initialize rule-set[...]: ... EOF``), which kills the whole TUN engine. This
helper NEVER emits a remote entry: it only returns ``type: local`` when a cached
``.srs`` file exists on disk, and ``None`` otherwise — callers must then drop the
rule (and its rules/dns-rules) from the config so no dangling references remain.

Local cache dir = ``CONFIG_DIR/rule_sets`` (or ``XENRAY_RULE_CACHE_DIR`` when
set). No network access happens here at all — offline by construction.
"""

from __future__ import annotations

import os

from src.core.logger import logger

_RULE_CACHE = os.getenv("XENRAY_RULE_CACHE_DIR", "") or ""

# Bundled offline rule-sets shipped with the app (assets/rules). Checked before
# the cache dir so the app never needs the network for common country/ads sets.
_ASSETS_RULES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # .../singbox/builders
    "..",
    "..",
    "..",
    "..",
    "assets",
    "rules",
)


def _default_cache_dir() -> str:
    try:
        from src.core.constants import CONFIG_DIR

        return os.path.join(CONFIG_DIR, "rule_sets")
    except Exception:
        return ""


def materialize_rule_set(tag: str, url: str) -> dict | None:
    """Return a ``type: local`` rule-set dict, or ``None`` when not cached.

    Offline-first: NEVER a ``type: remote`` entry (sing-box would fetch at
    startup and FATAL on EOF when the network drops mid-transfer). Callers must
    skip the rule (and its dependent rules/dns-rules) when ``None`` is returned.
    """
    name = url.rsplit("/", 1)[-1]
    bundled = os.path.normpath(os.path.join(_ASSETS_RULES_DIR, name))
    if os.path.exists(bundled):
        return {"tag": tag, "type": "local", "format": "binary", "path": bundled}
    cache_dir = _RULE_CACHE or _default_cache_dir()
    cached = os.path.normpath(os.path.join(cache_dir, name)) if cache_dir else ""
    if cached and os.path.exists(cached):
        return {"tag": tag, "type": "local", "format": "binary", "path": cached}
    logger.warning(
        f"[RuleSetUtils] Rule-set '{name}' not found (assets={bundled}, cache={cached or 'no cache dir'}); "
        f"dropping rule '{tag}' from config to avoid sing-box startup fetch."
    )
    return None
