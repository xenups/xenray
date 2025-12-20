"""Unit tests for ProfileManager."""
import pytest
from unittest.mock import Mock, call, patch

from src.ui.managers.profile_manager import ProfileManager


class TestProfileManager:
    """Test suite for ProfileManager."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for ProfileManager."""
        return {
            "connection_manager": Mock(),
            "connection_handler": Mock(),
            "ui_updater": Mock(),
            "config_manager": Mock(),
        }

    @pytest.fixture
    def profile_manager(self, mock_dependencies):
        """Create ProfileManager instance with mocked dependencies."""
        return ProfileManager(**mock_dependencies)

    def test_initialization(self, profile_manager):
        """Test ProfileManager initializes correctly."""
        assert profile_manager.selected_profile is None
        assert profile_manager.is_running is False

    def test_select_profile_without_reconnect(self, profile_manager, mock_dependencies):
        """Test selecting a profile without triggering reconnect."""
        profile = {"id": "test-1", "name": "Test Server"}

        profile_manager.select_profile(profile, trigger_reconnect=False)

        assert profile_manager.selected_profile == profile
        mock_dependencies["connection_manager"].disconnect.assert_not_called()

    def test_select_profile_with_reconnect_when_not_running(self, profile_manager, mock_dependencies):
        """Test selecting profile with reconnect flag when not running."""
        profile = {"id": "test-1", "name": "Test Server"}

        profile_manager.select_profile(profile, trigger_reconnect=True)

        assert profile_manager.selected_profile == profile
        # Should not reconnect because is_running is False
        mock_dependencies["connection_manager"].disconnect.assert_not_called()

    def test_select_profile_with_reconnect_when_running(self, profile_manager, mock_dependencies):
        """Test selecting profile with reconnect when already running."""
        profile = {"id": "test-1", "name": "Test Server"}
        profile_manager.is_running = True

        profile_manager.select_profile(profile, trigger_reconnect=True)

        assert profile_manager.selected_profile == profile
        # Should trigger reconnect
        mock_dependencies["connection_manager"].disconnect.assert_called_once()
        mock_dependencies["ui_updater"].assert_called()
        mock_dependencies["connection_handler"].connect_async.assert_called_once()

    def test_ui_update_callback(self, profile_manager):
        """Test UI update callback is called when profile is selected."""
        callback = Mock()
        profile_manager.set_ui_update_callback(callback)

        profile = {"id": "test-1", "name": "Test Server"}
        profile_manager.select_profile(profile)

        callback.assert_called_once_with(profile)

    def test_trigger_reconnect_when_not_running(self, profile_manager, mock_dependencies):
        """Test trigger_reconnect does nothing when not running."""
        profile_manager._selected_profile = {"id": "test-1"}

        profile_manager.trigger_reconnect()

        mock_dependencies["connection_manager"].disconnect.assert_not_called()

    def test_trigger_reconnect_when_no_profile(self, profile_manager, mock_dependencies):
        """Test trigger_reconnect does nothing when no profile selected."""
        profile_manager.is_running = True

        profile_manager.trigger_reconnect()

        mock_dependencies["connection_manager"].disconnect.assert_not_called()

    def test_trigger_reconnect_success(self, profile_manager, mock_dependencies):
        """Test successful reconnect when running with profile."""
        profile_manager.is_running = True
        profile_manager._selected_profile = {"id": "test-1"}

        profile_manager.trigger_reconnect()

        mock_dependencies["connection_manager"].disconnect.assert_called_once()
        mock_dependencies["ui_updater"].assert_called()
        mock_dependencies["connection_handler"].connect_async.assert_called_once()


    def test_selected_profile_property(self, profile_manager):
        """Test selected_profile property getter."""
        assert profile_manager.selected_profile is None

        profile = {"id": "test-1"}
        profile_manager._selected_profile = profile

        assert profile_manager.selected_profile == profile

    def test_is_running_state_changes(self, profile_manager):
        """Test is_running state can be changed."""
        assert profile_manager.is_running is False

        profile_manager.is_running = True
        assert profile_manager.is_running is True

        profile_manager.is_running = False
        assert profile_manager.is_running is False
