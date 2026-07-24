"""
Unit tests for PassiveLogMonitor.
"""
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from src.services.monitoring import PassiveLogMonitor


class TestPassiveLogMonitor(unittest.TestCase):
    def setUp(self):
        self.tmp_file = tempfile.mktemp()
        # Create file
        with open(self.tmp_file, "w") as f:
            f.write("Start log\n")

        self.monitor = PassiveLogMonitor(log_file_path=self.tmp_file)
        self.monitor.CHECK_INTERVAL = 0.1
        self.monitor.DEBOUNCE_SECONDS = 0.5

    def tearDown(self):
        self.monitor.stop()
        if os.path.exists(self.tmp_file):
            os.remove(self.tmp_file)

    def test_detects_error_keyword(self):
        callback = MagicMock()
        self.monitor._on_failure = callback

        self.monitor.start()
        time.sleep(0.2)

        # Append 3 transient errors to reach TRANSIENT_THRESHOLD
        with open(self.tmp_file, "a") as f:
            for i in range(3):
                f.write(f"2023/12/24 12:00:0{i} [Warning] failed to handler mux client connection: closed\n")

        # Callback is now threaded, give it a moment
        for _ in range(10):
            if callback.call_count > 0:
                break
            time.sleep(0.1)

        callback.assert_called_once()

    def test_debounce(self):
        callback = MagicMock()
        self.monitor._on_failure = callback
        self.monitor.DEBOUNCE_SECONDS = 1.0
        self.monitor.TRANSIENT_THRESHOLD = 3

        self.monitor.start()
        time.sleep(0.2)

        # Append 3 transient errors to reach TRANSIENT_THRESHOLD
        for i in range(3):
            with open(self.tmp_file, "a") as f:
                f.write(f"generic::error occurrence {i}\n")

        time.sleep(0.3)
        # Wait for callback
        for _ in range(5):
            if callback.call_count >= 1:
                break
            time.sleep(0.1)

        callback.assert_called_once()

        # Append another error (within debounce)
        with open(self.tmp_file, "a") as f:
            f.write("generic::error second wave\n")

        time.sleep(0.3)
        # Should still be called only once
        callback.assert_called_once()

        # Wait for debounce
        self.monitor.resume()  # Resume normally resets alert time, but here we just wait or force resume
        self.monitor.resume()

        # Need 3 more to trigger again
        for i in range(3):
            with open(self.tmp_file, "a") as f:
                f.write(f"generic::error third wave {i}\n")

        time.sleep(0.3)
        # Wait for callback
        for _ in range(5):
            if callback.call_count >= 2:
                break
            time.sleep(0.1)

        self.assertEqual(callback.call_count, 2)

    def test_log_rotation(self):
        callback = MagicMock()
        self.monitor._on_failure = callback

        self.monitor.start()
        time.sleep(0.2)

        # Rewrite file (simulating rotation/recreation) with 3 errors
        with open(self.tmp_file, "w") as f:
            f.write("New log start\n")
            for i in range(3):
                f.write(f"transport closed error {i}\n")

        time.sleep(0.5)
        # Wait for callback
        for _ in range(5):
            if callback.call_count >= 1:
                break
            time.sleep(0.1)

        callback.assert_called_once()

    def test_exponential_backoff(self):
        self.monitor.BASE_COOLDOWN_SECONDS = 0.1
        self.monitor.pause = MagicMock(wraps=self.monitor.pause)

        self.monitor.start()
        time.sleep(0.1)

        # 1st failure: write 3 transient lines to trigger
        with open(self.tmp_file, "a") as f:
            for i in range(3):
                f.write(f"generic::error 1.{i}\n")
        time.sleep(0.3)

        self.monitor.pause.assert_called_with(0.1)
        self.monitor.resume()  # Reset pause manually for speed

        # 2nd failure: 3 more lines
        with open(self.tmp_file, "a") as f:
            for i in range(3):
                f.write(f"generic::error 2.{i}\n")
        time.sleep(0.3)

        self.monitor.pause.assert_called_with(0.2)
        self.monitor.resume()

        # 3rd failure: 3 more lines
        with open(self.tmp_file, "a") as f:
            for i in range(3):
                f.write(f"generic::error 3.{i}\n")
        time.sleep(0.3)

        self.monitor.pause.assert_called_with(0.4)


if __name__ == "__main__":
    unittest.main()
