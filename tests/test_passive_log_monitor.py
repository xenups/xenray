"""
Unit tests for PassiveLogMonitor.
"""
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from src.services.passive_log_monitor import PassiveLogMonitor


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
        
        # Append error
        with open(self.tmp_file, "a") as f:
            f.write("Some info log\n")
            f.write("2023/12/24 12:00:00 [Warning] failed to handler mux client connection: closed\n")
            f.write("More info\n")
            
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
        
        self.monitor.start()
        time.sleep(0.2)
        
        # Append error 1
        with open(self.tmp_file, "a") as f:
            f.write("generic::error first\n")
            
        time.sleep(0.3)
        # Wait for callback
        for _ in range(5):
            if callback.call_count >= 1: break
            time.sleep(0.1)
        
        callback.assert_called_once()
        
        # Append error 2 (within debounce)
        with open(self.tmp_file, "a") as f:
            f.write("generic::error second\n")
            
        time.sleep(0.3)
        # Should still be called only once
        callback.assert_called_once()
        
        # Wait for debounce
        self.monitor.resume() # Resume normally resets alert time, but here we just wait or force resume
        # Actually monitor auto-pauses. Let's force resume or wait cooldown
        self.monitor.resume() 
        
        with open(self.tmp_file, "a") as f:
             f.write("generic::error third\n")
        
        time.sleep(0.3)
        # Wait for callback
        for _ in range(5):
            if callback.call_count >= 2: break
            time.sleep(0.1)
            
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
        for _ in range(5):
            if callback.call_count >= 1: break
            time.sleep(0.1)
        
        callback.assert_called_once()

    def test_exponential_backoff(self):
        self.monitor.BASE_COOLDOWN_SECONDS = 0.1
        self.monitor.pause = MagicMock(wraps=self.monitor.pause)
        
        self.monitor.start()
        time.sleep(0.1)
        
        # 1st failure
        with open(self.tmp_file, "a") as f:
            f.write("generic::error 1\n")
        time.sleep(0.2)
        
        self.monitor.pause.assert_called_with(0.1)
        self.monitor.resume() # Reset pause manually for speed
        
        # 2nd failure
        with open(self.tmp_file, "a") as f:
            f.write("generic::error 2\n")
        time.sleep(0.2)
        
        self.monitor.pause.assert_called_with(0.2)
        self.monitor.resume()
        
        # 3rd failure
        with open(self.tmp_file, "a") as f:
            f.write("generic::error 3\n")
        time.sleep(0.2)
        
        self.monitor.pause.assert_called_with(0.4)

if __name__ == '__main__':
    unittest.main()
