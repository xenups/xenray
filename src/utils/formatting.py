"""Shared byte-rate and byte-count formatting helpers."""

from __future__ import annotations


def format_speed(bytes_per_sec: float) -> str:
    """Format bytes-per-second into a dynamically-scaled human-readable speed string.

    - < 1024 B/s            -> ``"512 B/s"``
    - < 1024 KB/s (< 1 MB/s) -> ``"2.9 KB/s"``
    - < 1 GB/s               -> ``"1.4 MB/s"``
    - >= 1 GB/s              -> ``"1.23 GB/s"``
    """
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    if bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
    return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"
