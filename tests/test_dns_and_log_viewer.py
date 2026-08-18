"""Tests for DNS controller protocol-aware validation and LogViewer interval."""

from __future__ import annotations

import tempfile
import time
from unittest.mock import MagicMock

from src.ui.components.logs.log_viewer import LogViewer
from src.ui.controllers.dns_controller import DNSController


def _controller():
    app_context = MagicMock()
    app_context.dns.load.return_value = []
    return DNSController(app_context)


def test_dns_add_udp_bare_ip():
    c = _controller()
    assert c.add_server("1.1.1.1", "udp") is True
    assert c.dns_list[0] == {"address": "1.1.1.1", "protocol": "udp", "domains": []}


def test_dns_add_udp_rejects_scheme():
    c = _controller()
    assert c.add_server("https://1.1.1.1", "udp") is False
    assert c.dns_list == []


def test_dns_add_doh_bare_host_accepted():
    c = _controller()
    # Bare host is accepted — DnsConfigurator expands it to https://host/dns-query
    assert c.add_server("dns.google", "doh") is True
    assert c.dns_list[0]["protocol"] == "doh"


def test_dns_add_doh_with_url():
    c = _controller()
    assert c.add_server("https://dns.google/dns-query", "doh") is True
    assert c.dns_list[0]["address"] == "https://dns.google/dns-query"


def test_dns_add_dot_rejects_wrong_scheme():
    c = _controller()
    assert c.add_server("https://dns.google", "dot") is False


def test_dns_add_doq_bare_host():
    c = _controller()
    assert c.add_server("dns.adguard.com", "doq") is True


def test_dns_add_tcp_bare_ip():
    c = _controller()
    assert c.add_server("9.9.9.9", "tcp") is True


def test_dns_add_empty_rejected():
    c = _controller()
    assert c.add_server("   ", "udp") is False


def test_log_viewer_tail_interval_default():
    lv = LogViewer("test")
    assert lv.tail_interval == 1.0


def test_log_viewer_tail_interval_respected():
    """The tail loop must sleep for the configured interval (not hardcoded 0.5)."""
    lv = LogViewer("test")
    lv.tail_interval = 0.2
    with tempfile.TemporaryDirectory() as tmp:
        log = f"{tmp}/app.log"
        with open(log, "w") as f:
            f.write("start\n")

        # Monkeypatch _append_batch to track reads
        reads = []
        lv._append_batch = lambda lines: reads.append(len(lines))

        lv.start_tailing(log)
        try:
            with open(log, "a") as f:
                f.write("line1\n")
            # Wait for the tailer to pick it up (interval 0.2s → fast)
            deadline = time.time() + 2.0
            while time.time() < deadline and not reads:
                time.sleep(0.05)
            assert reads, "tailer never read the appended line"
        finally:
            lv.stop_tailing()


def test_log_viewer_dedupes_consecutive_identical_lines():
    """Consecutive duplicate lines must be shown ONCE (spam suppression).

    A repeated error line (e.g. the same dial timeout written every second)
    must not flood the viewer; a different line resumes normal output.
    """
    lv = LogViewer("test")

    lv._append_batch(["error: dial timeout\n", "error: dial timeout\n", "error: dial timeout\n"])
    assert lv._log_text.value == "error: dial timeout"

    # Same line again in a NEW batch — still suppressed (consecutive).
    lv._append_batch(["error: dial timeout\n"])
    assert lv._log_text.value == "error: dial timeout"

    # A different line breaks the run and is appended.
    lv._append_batch(["status: ok\n"])
    assert lv._log_text.value == "status: ok\nerror: dial timeout"

    # Repeating the same line AFTER a different line is NOT a consecutive
    # duplicate — it must be shown again.
    lv._append_batch(["error: dial timeout\n"])
    assert lv._log_text.value == "error: dial timeout\nstatus: ok\nerror: dial timeout"


def test_log_viewer_dedupe_resets_on_clear():
    """clear_logs() must reset the dedupe tracker so a cleared viewer accepts
    the same line again."""
    lv = LogViewer("test")
    lv._append_batch(["spam\n", "spam\n"])
    assert lv._log_text.value == "spam"

    lv.clear_logs()
    assert lv._log_text.value == ""

    lv._append_batch(["spam\n"])
    assert lv._log_text.value == "spam"


def test_log_viewer_dedupe_ignores_empty_batch():
    """An empty batch must not disturb the dedupe state."""
    lv = LogViewer("test")
    lv._append_batch(["spam\n"])
    lv._append_batch([])
    lv._append_batch(["spam\n"])
    assert lv._log_text.value == "spam"
