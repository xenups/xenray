"""Unit tests for CoreHealthMonitor (active health monitoring & crash teardown)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.core.event_bus import EVENT_CORE_CRASHED, EventBus
from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState
from src.services.monitoring.core_health_monitor import CoreHealthMonitor


@pytest.fixture
def test_bus():
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def fsm(test_bus):
    fsm_obj = ConnectionFSM(bus=test_bus)
    fsm_obj.transition_to(ConnectionState.CONNECTED, force=True)
    return fsm_obj


@pytest.mark.asyncio
async def test_singbox_crash_detection_and_cascading_kill(fsm, test_bus):
    crashed_events = []

    def crash_subscriber(payload):
        crashed_events.append(payload)

    test_bus.subscribe(EVENT_CORE_CRASHED, crash_subscriber)

    mock_xray = MagicMock()
    mock_xray.is_running.return_value = True
    mock_xray.pid = 1234

    mock_singbox = MagicMock()
    mock_singbox.is_running.return_value = False  # Simulating Sing-box process crash!
    mock_singbox.pid = 5678

    mock_routes = MagicMock()
    mock_dns = MagicMock()
    mock_toast = MagicMock()

    monitor = CoreHealthMonitor(
        xray_service=mock_xray,
        singbox_service=mock_singbox,
        route_manager_service=mock_routes,
        dns_configurator=mock_dns,
        fsm=fsm,
        bus=test_bus,
        toast_callback=mock_toast,
    )

    with (
        patch("src.utils.process_utils.ProcessUtils.is_running") as mock_is_running,
        patch("src.utils.process_utils.ProcessUtils.kill_process") as mock_kill,
    ):
        # PID 1234 (xray) is running, PID 5678 (singbox) is dead
        mock_is_running.side_effect = lambda pid: pid == 1234

        await monitor.handle_crash(crashed_engine="singbox", pid=5678)

        # 1. Verify EVENT_CORE_CRASHED event emitted
        assert len(crashed_events) == 1
        assert crashed_events[0]["crashed_engine"] == "singbox"
        assert crashed_events[0]["pid"] == 5678

        # 2. Verify cascading kill of remaining Xray-core process by exact PID (1234)
        mock_kill.assert_called_with(1234, force=True)

        # 3. Verify route and DNS cleanup executed
        mock_routes.cleanup_routes.assert_called_once()
        mock_dns.restore_dns.assert_called_once()

        # 4. Verify FSM transitioned to ERROR
        assert fsm.state == ConnectionState.ERROR

        # 5. Verify Toast Error displayed
        mock_toast.assert_called_once_with("اتصال به دلیل کرش هسته قطع شد", "error")


@pytest.mark.asyncio
async def test_xray_crash_detection_and_cascading_kill(fsm, test_bus):
    crashed_events = []
    test_bus.subscribe(EVENT_CORE_CRASHED, lambda p: crashed_events.append(p))

    mock_xray = MagicMock()
    mock_xray.is_running.return_value = False  # Xray crashed!
    mock_xray.pid = 1111

    mock_singbox = MagicMock()
    mock_singbox.is_running.return_value = True
    mock_singbox.pid = 2222

    mock_routes = MagicMock()
    mock_dns = MagicMock()

    monitor = CoreHealthMonitor(
        xray_service=mock_xray,
        singbox_service=mock_singbox,
        route_manager_service=mock_routes,
        dns_configurator=mock_dns,
        fsm=fsm,
        bus=test_bus,
    )

    with (
        patch("src.utils.process_utils.ProcessUtils.is_running") as mock_is_running,
        patch("src.utils.process_utils.ProcessUtils.kill_process") as mock_kill,
    ):
        mock_is_running.side_effect = lambda pid: pid == 2222

        await monitor.handle_crash(crashed_engine="xray", pid=1111)

        assert len(crashed_events) == 1
        assert crashed_events[0]["crashed_engine"] == "xray"

        # Cascading kill of Sing-box PID 2222
        mock_kill.assert_called_with(2222, force=True)
        assert fsm.state == ConnectionState.ERROR


def test_start_monitoring_uses_dedicated_daemon_thread(test_bus):
    """The health polling loop must NEVER run as an asyncio task on a running loop.

    Blocking process checks (psutil) inside the Flet UI event loop would starve
    it. start_monitoring must always isolate the loop onto a daemon thread.
    """
    fsm_obj = ConnectionFSM(bus=test_bus)
    monitor = CoreHealthMonitor(fsm=fsm_obj, bus=test_bus)

    monitor.start_monitoring()

    try:
        assert monitor._is_monitoring is True
        # Dedicated thread, never an asyncio task
        assert monitor._monitor_task is None
        assert monitor._monitor_thread is not None
        assert monitor._monitor_thread.daemon is True
        assert monitor._monitor_thread.is_alive()
    finally:
        monitor.stop_monitoring()
        if monitor._monitor_thread:
            monitor._monitor_thread.join(timeout=2.0)
    assert monitor._monitor_thread.is_alive() is False


@pytest.mark.asyncio
async def test_start_monitoring_never_schedules_task_on_running_loop(fsm, test_bus):
    """Even when called from a running event loop, no task is created on it."""
    monitor = CoreHealthMonitor(fsm=fsm, bus=test_bus)

    # Called from within a running loop: the OLD code created a loop task here.
    monitor.start_monitoring()

    try:
        assert monitor._monitor_task is None
        assert monitor._monitor_thread is not None
    finally:
        monitor.stop_monitoring()
        if monitor._monitor_thread:
            monitor._monitor_thread.join(timeout=2.0)


def test_poll_once_detects_crash_and_triggers_handling(fsm, test_bus):
    """A single health tick detects a dead engine and triggers crash handling."""
    mock_xray = MagicMock()
    mock_xray.is_running = lambda: False  # Xray crashed
    mock_xray.pid = 1111

    mock_singbox = MagicMock()
    mock_singbox.is_running = lambda: True
    mock_singbox.pid = 2222

    monitor = CoreHealthMonitor(
        xray_service=mock_xray,
        singbox_service=mock_singbox,
        fsm=fsm,
        bus=test_bus,
    )

    with (
        patch("src.utils.process_utils.ProcessUtils.is_running") as mock_is_running,
        patch.object(monitor, "handle_crash_sync") as mock_handle,
    ):
        mock_is_running.side_effect = lambda pid: pid == 2222

        crashed = monitor._poll_once()

        assert crashed is True
        mock_handle.assert_called_once_with(crashed_engine="xray", pid=1111)


@pytest.mark.asyncio
async def test_health_loop_offloads_blocking_checks_to_thread(fsm, test_bus):
    """The async loop variant must offload blocking process checks via to_thread."""
    from unittest.mock import AsyncMock

    monitor = CoreHealthMonitor(fsm=fsm, bus=test_bus)
    monitor._is_monitoring = True

    polled = []

    async def fake_to_thread(fn, *args, **kwargs):
        polled.append(fn)
        monitor._is_monitoring = False  # stop after the first tick
        return fn(*args, **kwargs)

    with (
        patch(
            "src.services.monitoring.core_health_monitor.asyncio.to_thread",
            side_effect=fake_to_thread,
        ),
        patch(
            "src.services.monitoring.core_health_monitor.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        await monitor._health_loop()

    assert polled == [monitor._poll_once]
    monitor._is_monitoring = False
