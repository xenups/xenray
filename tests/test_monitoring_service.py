"""Unit tests for MonitoringService."""
from unittest.mock import Mock

import pytest

from src.ui.managers.monitoring_service import MonitoringService


class TestMonitoringService:
    """Test suite for MonitoringService."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for MonitoringService."""
        return {
            "connection_manager": Mock(),
            "connection_handler": Mock(),
            "ui_updater": Mock(),
            "toast_manager": Mock(),
        }

    @pytest.fixture
    def monitoring_service(self, mock_dependencies):
        """Create MonitoringService instance with mocked dependencies."""
        service = MonitoringService(
            connection_manager=mock_dependencies["connection_manager"],
            connection_handler=mock_dependencies["connection_handler"],
        )
        service.setup(
            ui_updater=mock_dependencies["ui_updater"],
            toast_manager=mock_dependencies["toast_manager"],
        )
        return service

    def test_initialization(self, monitoring_service):
        """Test MonitoringService initializes correctly."""
        assert monitoring_service.is_running is False
        assert monitoring_service._monitoring_active is False
        assert monitoring_service._monitoring_thread is None

    def test_start_monitoring_loop(self, monitoring_service):
        """Test starting monitoring loop."""
        monitoring_service.start_monitoring_loop()

        assert monitoring_service._monitoring_active is True
        assert monitoring_service._monitoring_thread is not None
        assert monitoring_service._monitoring_thread.daemon is True

        # Cleanup
        monitoring_service.stop_monitoring()

    def test_start_monitoring_loop_already_active(self, monitoring_service):
        """Test starting monitoring when already active does nothing."""
        monitoring_service.start_monitoring_loop()
        first_thread = monitoring_service._monitoring_thread

        monitoring_service.start_monitoring_loop()
        second_thread = monitoring_service._monitoring_thread

        # Should be the same thread
        assert first_thread is second_thread

        # Cleanup
        monitoring_service.stop_monitoring()

    def test_stop_monitoring(self, monitoring_service):
        """Test stopping monitoring loop."""
        monitoring_service.start_monitoring_loop()
        assert monitoring_service._monitoring_active is True

        monitoring_service.stop_monitoring()

        assert monitoring_service._monitoring_active is False

    def test_is_running_state_changes(self, monitoring_service):
        """Test is_running state can be changed."""
        assert monitoring_service.is_running is False

        monitoring_service.is_running = True
        assert monitoring_service.is_running is True

        monitoring_service.is_running = False
        assert monitoring_service.is_running is False
