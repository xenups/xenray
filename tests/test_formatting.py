"""Unit tests for the shared speed/byte formatting utility."""

from __future__ import annotations

import pytest

from src.utils.formatting import format_speed


@pytest.mark.parametrize(
    ("bps", "expected"),
    [
        (0.0, "0 B/s"),
        (512.0, "512 B/s"),
        (1023.0, "1023 B/s"),
        (2048.0, "2.0 KB/s"),
        (2969.6, "2.9 KB/s"),
        (51200.0, "50.0 KB/s"),
        (1_000_000.0, "976.6 KB/s"),
        (1_048_576.0, "1.0 MB/s"),
        (1_468_006.4, "1.4 MB/s"),
        (5_000_000.0, "4.8 MB/s"),
        (1_500_000_000.0, "1.40 GB/s"),
    ],
)
def test_format_speed_scales_units_dynamically(bps, expected):
    assert format_speed(bps) == expected


def test_format_speed_low_download_no_longer_rounds_to_zero_mbs():
    assert format_speed(2969.6) != "0.0 MB/s"
    assert "KB/s" in format_speed(2969.6)
