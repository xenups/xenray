"""
Unit tests for PassiveLogMonitor.
"""

import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from loguru import logger as loguru_logger

from src.services.monitoring import PassiveLogMonitor


def _capture_warnings():
    """Install a loguru sink that collects WARNING+ records, returns (records, handler_id)."""
    records = []

    def collector(message):
        records.append(message.record["message"])

    handler_id = loguru_logger.add(collector, level="WARNING")
    return records, handler_id


class TestPassiveLogMonitor(unittest.TestCase):
    def setUp(self):
        self.tmp_file = tempfile.mktemp()
        # Create file
        with open(self.tmp_file, "w") as f:
            f.write("Start log\n")

        self.monitor = PassiveLogMonitor(log_files=[self.tmp_file])
        self.monitor.CHECK_INTERVAL = 0.1
        self.monitor.DEBOUNCE_SECONDS = 0.5

    def tearDown(self):
        self.monitor.stop()
        if os.path.exists(self.tmp_file):
            os.remove(self.tmp_file)

    def _wait_for_callback(self, callback, count=1, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if callback.call_count >= count:
                return True
            time.sleep(0.05)
        return False

    def test_detects_error_keyword(self):
        callback = MagicMock()
        self.monitor._on_failure = callback

        self.monitor.start()
        time.sleep(0.2)

        # Append error
        with open(self.tmp_file, "a") as f:
            f.write("Some info log\n")
            f.write("2023/12/24 12:00:00 [Warning] failed to handler mux client connection: closed\n")
            f.write("More info\n")

        # Callback is now threaded, give it a moment
        assert self._wait_for_callback(callback), "callback not called"

        callback.assert_called_once()

    def test_debounce(self):
        callback = MagicMock()
        self.monitor._on_failure = callback
        self.monitor.DEBOUNCE_SECONDS = 1.0

        self.monitor.start()
        time.sleep(0.2)

        # Append error 1
        with open(self.tmp_file, "a") as f:
            f.write("generic::error first\n")

        time.sleep(0.3)
        # Wait for callback
        assert self._wait_for_callback(callback, 1), "callback 1 not called"

        callback.assert_called_once()

        # Append error 2 (within debounce)
        with open(self.tmp_file, "a") as f:
            f.write("generic::error second\n")

        time.sleep(0.3)
        # Should still be called only once
        callback.assert_called_once()

        # Wait for debounce
        self.monitor.resume()  # Resume normally resets alert time, but here we just wait or force resume
        # Actually monitor auto-pauses. Let's force resume or wait cooldown
        self.monitor.resume()

        with open(self.tmp_file, "a") as f:
            f.write("generic::error third\n")

        time.sleep(0.3)
        # Wait for callback
        assert self._wait_for_callback(callback, 2), "callback 2 not called"

        self.assertEqual(callback.call_count, 2)

    def test_log_rotation(self):
        callback = MagicMock()
        self.monitor._on_failure = callback

        self.monitor.start()
        time.sleep(0.2)

        # Rewrite file (simulating rotation/recreation)
        with open(self.tmp_file, "w") as f:
            f.write("New log start\n")
            f.write("transport closed error\n")

        time.sleep(0.5)
        # Wait for callback
        assert self._wait_for_callback(callback, 1), "callback not called after rotation"

        callback.assert_called_once()

    def test_dns_fallback_logs_warning_not_failure(self):
        callback = MagicMock()
        self.monitor._on_failure = callback
        records, handler_id = _capture_warnings()
        try:
            self.monitor._process_line(
                "2023/12/24 12:00:00 [Warning] app/dns: failed to resolve domain example.com, using 1.1.1.1"
            )
        finally:
            loguru_logger.remove(handler_id)

        callback.assert_not_called()
        assert len(records) == 1
        assert "[DNS Warning]" in records[0]
        assert "example.com" in records[0]
        assert "Falling back to secondary Remote DNS" in records[0]

    def test_dns_fallback_other_keywords(self):
        callback = MagicMock()
        self.monitor._on_failure = callback
        self.monitor.DEBOUNCE_SECONDS = 0.0
        records, handler_id = _capture_warnings()
        try:
            self.monitor._process_line("[Warning] DNS fallback triggered for proxy.example.org")
            self.monitor._process_line("[Warning] app/dns: failed to lookup ip for dns.google")
        finally:
            loguru_logger.remove(handler_id)

        callback.assert_not_called()
        assert len(records) == 2

    def test_dns_fallback_debounced(self):
        callback = MagicMock()
        self.monitor._on_failure = callback
        self.monitor.DEBOUNCE_SECONDS = 10.0
        records, handler_id = _capture_warnings()
        try:
            self.monitor._process_line("failed to resolve domain one.com")
            self.monitor._process_line("failed to resolve domain two.com")
        finally:
            loguru_logger.remove(handler_id)

        assert len(records) == 1

    def test_exponential_backoff(self):
        # Contract (F6): the monitor itself no longer self-pauses — all
        # reconnect backoff is owned by AutoReconnectService. The per-source
        # debounce (DEBOUNCE_SECONDS) is the duplicate-signal guard, and
        # consecutive alerts still increment _consecutive_failures so the
        # service can compute its own exponential backoff.
        self.monitor.DEBOUNCE_SECONDS = 0.0  # disable debounce for this test

        self.monitor.start()
        time.sleep(0.1)

        # 1st failure
        with open(self.tmp_file, "a") as f:
            f.write("generic::error 1\n")
        time.sleep(0.2)

        self.assertEqual(self.monitor._consecutive_failures, 1)
        self.assertFalse(self.monitor._paused)
        self.assertEqual(self.monitor._paused_until, 0.0)

        # 2nd failure
        with open(self.tmp_file, "a") as f:
            f.write("generic::error 2\n")
        time.sleep(0.2)

        self.assertEqual(self.monitor._consecutive_failures, 2)
        self.assertFalse(self.monitor._paused)
        self.assertEqual(self.monitor._paused_until, 0.0)

        # 3rd failure
        with open(self.tmp_file, "a") as f:
            f.write("generic::error 3\n")
        time.sleep(0.2)

        self.assertEqual(self.monitor._consecutive_failures, 3)
        self.assertFalse(self.monitor._paused)
        self.assertEqual(self.monitor._paused_until, 0.0)

    def test_fatal_config_line_does_not_trigger(self):
        """F4: a config line containing 'fatal' (e.g. log.level) must NOT fire the callback."""
        callback = MagicMock()
        self.monitor._on_failure = callback

        self.monitor._process_line('log.level: "fatal"')
        self.monitor._process_line("2026/01/01 10:00:00 [WARN] config: level fatal is invalid")
        callback.assert_not_called()

    def test_fatal_failure_line_triggers(self):
        """F4: a real fatal failure line MUST fire the callback."""
        callback = MagicMock()
        self.monitor._on_failure = callback

        self.monitor.start()
        try:
            self.monitor._process_line("2026/01/01 10:00:00 [FATAL] fatal: failed to create tun: permission denied")
            assert self._wait_for_callback(callback), "callback not called"
            payload = callback.call_args[0][0]
            self.assertEqual(payload["source"], "xray")
            self.assertIn("failed to create tun", payload["line"])
        finally:
            self.monitor.stop()


if __name__ == "__main__":
    unittest.main()
