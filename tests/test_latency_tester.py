"""Tests for the v2rayNG-style latency engine (204 header-only probe + async batch)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.services.connection_tester import GENERATE_204_URLS, ConnectionTester
from src.services.latency_tester import LatencyTester


def _fake_resp(status_code: int = 204) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_probe_204_uses_gstatic_and_streams_headers_only():
    with patch("src.services.connection_tester.requests.get", return_value=_fake_resp(204)) as mock_get:
        ok, latency = ConnectionTester._probe_204({"http": "http://127.0.0.1:10808"})

    assert ok is True
    assert 0 <= latency < 100
    assert mock_get.call_count == 1
    assert mock_get.call_args.args[0] == GENERATE_204_URLS[0]  # gstatic first
    assert mock_get.call_args.kwargs["stream"] is True  # never downloads a body
    assert mock_get.call_args.kwargs["timeout"] == 3.0  # hard per-node timeout


def test_probe_204_fails_over_to_cloudflare_on_timeout():
    resp = _fake_resp(204)
    with patch(
        "src.services.connection_tester.requests.get",
        side_effect=[__import__("requests").exceptions.Timeout(), resp],
    ) as mock_get:
        ok, latency = ConnectionTester._probe_204({})

    assert ok is True
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].args[0] == GENERATE_204_URLS[1]  # cloudflare fallback


def test_probe_204_returns_failure_when_all_urls_fail():
    with patch(
        "src.services.connection_tester.requests.get",
        side_effect=[__import__("requests").exceptions.Timeout()] * len(GENERATE_204_URLS),
    ) as mock_get:
        ok, latency = ConnectionTester._probe_204({})

    assert ok is False
    assert latency == 0
    assert mock_get.call_count == len(GENERATE_204_URLS)


def test_batch_tests_all_profiles_concurrently():
    profiles = [{"id": f"p{i}", "config": {"x": i}} for i in range(5)]
    completed = []
    all_done = []

    tester = LatencyTester(
        on_test_complete=lambda p, s, r, c: completed.append(p["id"]),
        on_all_complete=lambda: all_done.append(True),
    )

    with patch(
        "src.services.latency_tester.ConnectionTester.test_connection_sync",
        return_value=(True, "Latency: 123ms", None),
    ):
        tester.test_profiles(profiles, fetch_flags=False)

        for _ in range(100):
            if not tester.is_testing:
                break
            time.sleep(0.05)

    assert not tester.is_testing
    assert sorted(completed) == [f"p{i}" for i in range(5)]
    assert all_done == [True]
    # Every profile got a cached result.
    for i in range(5):
        cached = tester.get_cached_result(f"p{i}")
        assert cached is not None
        assert cached[2] == 123
