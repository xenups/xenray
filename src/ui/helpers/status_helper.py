"""Status formatting helper for concise, colloquial UI displays across all languages."""
from __future__ import annotations

import re
from typing import Optional

from src.core.i18n import t


def get_short_status_label(raw_status: Optional[str] = None) -> str:
    """
    Format and transform UI status labels across all i18n languages into
    short, colloquial 1-3 word strings with all trailing dots/ellipses stripped.

    Design rules:
    - If the input is already ≤ 3 words (post-strip), pass it through as-is.
      This respects user-crafted colloquial translations like "Checking Vibe",
      "Plan B Mode", "Almost There", "Engine Start" etc.
    - Only apply intent-mapping for clearly long raw backend strings that have
      NOT been translated yet (e.g., full English sentences from old log messages).
    - Always strip trailing ellipses/dots and emoji.

    Examples:
        - "Connecting..."          -> t("app.connecting")  [long + ellipsis]
        - "Checking Vibe"          -> "Checking Vibe"       [already short, pass through]
        - "Engine Start"           -> "Engine Start"         [already short, pass through]
        - "Error timeout occurred..."> t("connection.error") [long + error keyword]
    """
    if not raw_status or not isinstance(raw_status, str):
        return t("app.disconnected")

    # 1. Strip trailing dots, ellipses (both ASCII ... and Unicode …), whitespace, and trailing emojis
    clean = raw_status.replace("…", "").strip()
    clean = re.sub(r"\.+$", "", clean).strip()
    clean = re.sub(r"[\U0001F000-\U0001FFFF\U00002700-\U000027BF\u2600-\u26FF]+\s*$", "", clean).strip()

    if not clean:
        return t("app.disconnected")

    # 2. If the string is already short (≤ 3 words), pass it through directly.
    #    This honours curated colloquial translations without remapping them.
    words = clean.split()
    if len(words) <= 3:
        return clean

    # 3. For LONG raw strings only, apply intent-based mapping.
    lower = clean.lower()

    # No Internet (MUST be checked before general connected check)
    if any(
        k in lower
        for k in [
            "no internet",
            "no_internet",
            "no net",
            "connected_no_internet",
            "without internet",
            "без интернета",
            "بدون نت",
            "بدون اینترنت",
            "没网",
            "left on read",
        ]
    ):
        return t("connection.connected_no_internet")

    # Errors / Failures / Timeouts
    if any(k in lower for k in ["fail", "error", "timeout", "hold tight", "دست نگه دار", "稍等", "подождите"]):
        return t("connection.error")

    # Checking / Latency test
    if any(k in lower for k in ["check", "verif", "looking", "بررسی", "探索"]):
        return t("app.checking")

    # Reconnecting
    if "reconnect" in lower:
        return t("connection.reconnecting")

    # Disconnected
    if any(k in lower for k in ["disconnected", "unlinking", "قطع شده", "已断开", "отключено"]):
        return t("app.disconnected")

    # Connected
    if any(k in lower for k in ["connected", "reconnected", "success", "متصل شد", "已连接", "подключено"]):
        return t("app.connected")

    # Connecting / Waking
    if any(
        k in lower
        for k in ["connecting", "loading", "starting", "initializing", "waking", "در حال بیداری", "唤醒中", "просыпаюсь"]
    ):
        return t("app.connecting")

    # 4. Final fallback: truncate to first 3 words and strip trailing conjunctions
    truncated = " ".join(words[:3])
    return re.sub(r"\s+(&|and|\+|\,)\s*$", "", truncated, flags=re.IGNORECASE).strip()
