"""Profile Manager - Handles profile selection and testing."""
from typing import Callable, Optional

from loguru import logger

from src.services.connection_tester import ConnectionTester


class ProfileManager:
    """Manages profile selection, testing, and reconnection logic."""

    def __init__(
        self,
        connection_manager,
        connection_handler,
        ui_updater: Callable,
    ):
        """
        Initialize ProfileManager with injected dependencies.

        Args:
            connection_manager: ConnectionManager instance
            connection_handler: ConnectionHandler instance
            ui_updater: Callable for updating UI
        """
        self._connection_manager = connection_manager
        self._connection_handler = connection_handler
        self._ui_call = ui_updater
        self._selected_profile: Optional[dict] = None

        # Callback for UI updates when profile is selected
        self._on_profile_selected_ui: Optional[Callable[[dict], None]] = None

        # Will be set by MainWindow
        self.is_running = False

    @property
    def selected_profile(self) -> Optional[dict]:
        """Get currently selected profile."""
        return self._selected_profile

    def set_ui_update_callback(self, callback: Callable[[dict], None]):
        """Set callback for UI updates when profile is selected."""
        self._on_profile_selected_ui = callback

    def select_profile(self, profile: dict, trigger_reconnect: bool = True):
        """
        Select a profile and optionally trigger reconnection.

        Args:
            profile: Profile dictionary to select
            trigger_reconnect: Whether to reconnect if already running
        """
        self._selected_profile = profile

        # Update UI if callback is set
        if self._on_profile_selected_ui:
            self._on_profile_selected_ui(profile)

        # Trigger reconnection if already running
        if trigger_reconnect and self.is_running:
            self.trigger_reconnect()

    def test_profile(self, profile: dict, callback: Callable):
        """
        Test profile connection and fetch country data.

        Args:
            profile: Profile to test
            callback: Callback function(success, result_str, country_data, profile)
        """
        config = profile.get("config", {})

        def test_callback(success, result_str, country_data):
            callback(success, result_str, country_data, profile)

        ConnectionTester.test_connection(config, test_callback, fetch_country=True)

    def trigger_reconnect(self):
        """Handle transparent reconnection when server changes while running."""
        if not self.is_running or not self._selected_profile:
            return

        logger.info("[ProfileManager] Triggering reconnect with new profile")

        # Disconnect current connection
        self._connection_manager.disconnect()

        # Reset UI to disconnected state briefly
        self._ui_call(self._connection_handler.reset_ui_disconnected)

        # Reconnect with new profile
        self._connection_handler.connect_async()
