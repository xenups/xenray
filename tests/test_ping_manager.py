"""Tests for the PingManager priority queue / single-flight lock."""

from __future__ import annotations

import time
from threading import Event

from src.services.ping_service import PRIORITY_IMPORT, PRIORITY_INTERVAL, PRIORITY_MANUAL, PingManager


def _wait_for(condition, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_manual_priority_preempts_interval():
    order = []
    mgr = PingManager()

    # Interval (P3) queued FIRST, manual (P1) queued SECOND.
    mgr.submit(PRIORITY_INTERVAL, "interval:a", lambda: order.append("interval"))
    mgr.submit(PRIORITY_MANUAL, "manual:x", lambda: order.append("manual"))

    assert _wait_for(lambda: len(order) == 2)
    # Manual runs first despite being enqueued second (priority ordering).
    assert order == ["manual", "interval"]


def test_import_priority_precedes_interval():
    order = []
    mgr = PingManager()

    mgr.submit(PRIORITY_INTERVAL, "interval:a", lambda: order.append("interval"))
    mgr.submit(PRIORITY_IMPORT, "import:b", lambda: order.append("import"))

    assert _wait_for(lambda: len(order) == 2)
    assert order == ["import", "interval"]


def test_deduplication_skips_same_key():
    calls = []
    mgr = PingManager()
    release = Event()

    def pending():
        calls.append(1)
        release.wait(timeout=3.0)

    assert mgr.submit(PRIORITY_INTERVAL, "server-a", pending) is True
    # Same key already queued/running -> rejected.
    assert mgr.submit(PRIORITY_INTERVAL, "server-a", pending) is False
    # A different key is accepted.
    assert mgr.submit(PRIORITY_INTERVAL, "server-b", pending) is True

    time.sleep(0.2)
    assert len(calls) == 1  # only server-a started so far (server-b waits its turn)
    release.set()
    assert _wait_for(lambda: len(calls) == 2)
    assert len(calls) == 2


def test_interval_skips_cycle_while_higher_priority_work_pending():
    mgr = PingManager()
    release = Event()

    # Manual op is running (blocked).
    mgr.submit(PRIORITY_MANUAL, "manual:x", lambda: release.wait(timeout=3.0))

    time.sleep(0.2)
    # While the manual op is in flight, the interval must skip its cycle.
    assert mgr.skip_interval() is True
    release.set()
    assert _wait_for(lambda: not mgr.is_busy())
    assert mgr.skip_interval() is False


def test_only_one_operation_executes_at_a_time():
    active = 0
    max_active = 0
    lock = __import__("threading").Lock()
    mgr = PingManager()
    done = Event()
    counter = {"done": 0}

    def slow():
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
            counter["done"] += 1
            if counter["done"] == 4:
                done.set()

    for i in range(4):
        mgr.submit(PRIORITY_INTERVAL, f"s{i}", slow)

    assert done.wait(timeout=3.0)
    assert max_active == 1  # never two pings overlapping


def test_submit_and_get_future_resolves_with_result():
    mgr = PingManager()
    future = mgr.submit_and_get_future(PRIORITY_MANUAL, "k", lambda: "138ms")
    assert future is not None
    assert future.result(timeout=3.0) == "138ms"


def test_submit_and_get_future_dedups_same_key():
    mgr = PingManager()
    release = Event()

    def pending():
        release.wait(timeout=3.0)
        return "x"

    assert mgr.submit_and_get_future(PRIORITY_MANUAL, "k", pending) is not None
    assert mgr.submit_and_get_future(PRIORITY_MANUAL, "k", pending) is None
    release.set()
