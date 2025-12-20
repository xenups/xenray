"""Connection Handler - Manages connection lifecycle."""

from __future__ import annotations

import json
import os
import threading
from typing import Callable, Optional

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.constants import SINGBOX_LOG_FILE, TMPDIR, XRAY_LOG_FILE
from src.core.i18n import t
from src.core.logger import logger
from src.core.types import ConnectionMode
from src.services.network_stats import NetworkStatsService


class ConnectionHandler:
    """Handles connection lifecycle (connect, disconnect, reconnect)."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        config_manager: ConfigManager,
        network_stats: NetworkStatsService,
    ):
        self._connection_manager = connection_manager
        self._config_manager = config_manager
        self._network_stats = network_stats

        self._ui_helper = None
        self._connection_button = None
        self._status_display = None
        self._log_viewer = None
        self._toast = None
        self._systray = None
        self._logs_drawer_component = None
        self._latency_monitor_handler = None

        # State getters and setters
        self._is_running_getter: Optional[Callable[[], bool]] = None
        self._is_running_setter: Optional[Callable[[bool], None]] = None
        self._connecting_getter: Optional[Callable[[], bool]] = None
        self._connecting_setter: Optional[Callable[[bool], None]] = None
        self._selected_profile_getter: Optional[Callable[[], Optional[dict]]] = None
        self._current_mode_getter: Optional[Callable[[], ConnectionMode]] = None
        self._update_horizon_glow_callback: Optional[Callable[[str], None]] = None

        # Service state setters
        self._profile_manager_is_running_setter: Optional[Callable[[bool], None]] = None
        self._monitoring_service_is_running_setter: Optional[Callable[[bool], None]] = (
            None
        )

    def setup(
        self,
        ui_helper,
        connection_button,
        status_display,
        log_viewer,
        toast,
        systray,
        logs_drawer_component,
        latency_monitor_handler,
        is_running_getter,
        is_running_setter,
        connecting_getter,
        connecting_setter,
        selected_profile_getter,
        current_mode_getter,
        update_horizon_glow_callback,
        profile_manager_is_running_setter,
        monitoring_service_is_running_setter,
    ):
        """Bind UI components and state callbacks to the handler."""
        self._ui_helper = ui_helper
        self._connection_button = connection_button
        self._status_display = status_display
        self._log_viewer = log_viewer
        self._toast = toast
        self._systray = systray
        self._logs_drawer_component = logs_drawer_component
        self._latency_monitor_handler = latency_monitor_handler
        self._is_running_getter = is_running_getter
        self._is_running_setter = is_running_setter
        self._connecting_getter = connecting_getter
        self._connecting_setter = connecting_setter
        self._selected_profile_getter = selected_profile_getter
        self._current_mode_getter = current_mode_getter
        self._update_horizon_glow_callback = update_horizon_glow_callback
        self._profile_manager_is_running_setter = profile_manager_is_running_setter
        self._monitoring_service_is_running_setter = (
            monitoring_service_is_running_setter
        )

    def connect_async(self):
        """Start connection in background thread."""
        if self._connecting_getter and self._connecting_getter():
            return
        if self._connecting_setter:
            self._connecting_setter(True)

        # Show connecting animation immediately
        if self._ui_helper:
            if self._connection_button:
                self._ui_helper.call(self._connection_button.set_connecting)
            if self._status_display:
                self._ui_helper.call(self._status_display.set_initializing)
            if self._update_horizon_glow_callback:
                self._ui_helper.call(
                    lambda: self._update_horizon_glow_callback("connecting")
                )

        threading.Thread(target=self._perform_connect_task, daemon=True).start()

    def reconnect(self):
        """Fast reconnect for server switching while running."""
        if self._connecting_getter and self._connecting_getter():
            return

        if self._connecting_setter:
            self._connecting_setter(True)

        # Visually switch to "Connecting" (Amber) immediately
        if self._ui_helper:
            if self._connection_button:
                self._ui_helper.call(self._connection_button.set_connecting)
            if self._status_display:
                self._ui_helper.call(self._status_display.set_initializing)
            if self._update_horizon_glow_callback:
                self._ui_helper.call(
                    lambda: self._update_horizon_glow_callback("connecting")
                )

        def fast_reconnect_task():
            try:
                # 1. Kill current connection silently
                if self._is_running_setter:
                    self._is_running_setter(False)
                if self._profile_manager_is_running_setter:
                    self._profile_manager_is_running_setter(False)
                if self._monitoring_service_is_running_setter:
                    self._monitoring_service_is_running_setter(False)

                try:
                    self._connection_manager.disconnect()
                except Exception:
                    pass

                # 2. Immediately start new connection
                self._perform_connect_task()
            except Exception as e:
                logger.error(f"Error in fast_reconnect_task: {e}")
                if self._connecting_setter:
                    self._connecting_setter(False)
                if self._ui_helper:
                    self._ui_helper.call(self.reset_ui_disconnected)

        threading.Thread(target=fast_reconnect_task, daemon=True).start()

    def _perform_connect_task(self):
        """Core connection logic reused by connect_async and reconnect."""
        try:
            # Check Internet Connectivity
            from src.utils.network_utils import NetworkUtils

            if not NetworkUtils.check_internet_connection():
                if self._connecting_setter:
                    self._connecting_setter(False)
                if self._ui_helper:
                    self._ui_helper.call(self.reset_ui_disconnected)
                if self._toast:
                    self._toast.error(t("connection.no_internet"), 3000)
                return

            selected_profile = (
                self._selected_profile_getter()
                if self._selected_profile_getter
                else None
            )
            profile_config = selected_profile.get("config") if selected_profile else {}

            current_mode = (
                self._current_mode_getter()
                if self._current_mode_getter
                else ConnectionMode.PROXY
            )
            mode_str = "vpn" if current_mode == ConnectionMode.VPN else "proxy"

            os.makedirs(TMPDIR, exist_ok=True)

            # Start logging
            if self._log_viewer:
                app_log = os.path.join(TMPDIR, "xenray.log")
                if current_mode == ConnectionMode.VPN:
                    self._log_viewer.start_tailing(
                        app_log, XRAY_LOG_FILE, SINGBOX_LOG_FILE
                    )
                else:
                    self._log_viewer.start_tailing(app_log, XRAY_LOG_FILE)

            temp_config_path = os.path.join(TMPDIR, "current_config.json")
            with open(temp_config_path, "w", encoding="utf-8") as f:
                json.dump(profile_config, f)

            def on_step(step_msg: str):
                if self._ui_helper and self._status_display:
                    self._ui_helper.call(self._status_display.set_step, step_msg)

            success = self._connection_manager.connect(
                temp_config_path, mode_str, step_callback=on_step
            )

            if not success:
                if self._connecting_setter:
                    self._connecting_setter(False)
                if self._ui_helper:
                    self._ui_helper.call(self.reset_ui_disconnected)
                if self._toast:
                    self._toast.error(t("status.connection_failed"), 3000)
                return

            if self._is_running_setter:
                self._is_running_setter(True)
            if self._profile_manager_is_running_setter:
                self._profile_manager_is_running_setter(True)
            if self._monitoring_service_is_running_setter:
                self._monitoring_service_is_running_setter(True)

            # Post-Connection Internet Check
            import time

            time.sleep(1)

            if self._ui_helper and self._status_display:
                self._ui_helper.call(
                    self._status_display.set_step, t("connection.checking_network")
                )

            proxy_port = self._config_manager.get_proxy_port()
            if not NetworkUtils.check_proxy_connectivity(proxy_port):
                logger.error("Post-connection internet check failed")
                if self._connecting_setter:
                    self._connecting_setter(False)
                self._connection_manager.disconnect()
                if self._ui_helper:
                    self._ui_helper.call(self.reset_ui_disconnected)
                if self._toast:
                    self._toast.warning(t("connection.connected_no_internet"), 3000)
                return

            if self._connecting_setter:
                self._connecting_setter(False)

            if self._ui_helper:
                if self._status_display:
                    self._ui_helper.call(
                        self._status_display.set_connected,
                        country_data=selected_profile,
                    )
                if self._connection_button:
                    self._ui_helper.call(self._connection_button.set_connected)
                if self._update_horizon_glow_callback:
                    self._ui_helper.call(
                        lambda: self._update_horizon_glow_callback("connected")
                    )

            # Update system tray state
            if self._systray:
                self._systray.update_state()

            # Start network stats service
            if self._network_stats:
                self._network_stats.start()
                if self._logs_drawer_component and self._ui_helper:
                    self._ui_helper.call(self._logs_drawer_component.show_stats, True)

        except Exception as e:
            logger.error(f"Error in _perform_connect_task: {e}")
            if self._connecting_setter:
                self._connecting_setter(False)
            if self._ui_helper:
                self._ui_helper.call(self.reset_ui_disconnected)

    def disconnect(self):
        """Disconnect from VPN/Proxy."""
        is_running = self._is_running_getter() if self._is_running_getter else False
        if not is_running:
            return

        # Show disconnecting UI immediately
        if self._ui_helper:
            if self._connection_button:
                self._ui_helper.call(self._connection_button.set_disconnecting)
            if self._status_display:
                self._ui_helper.call(self._status_display.set_disconnecting)
            if self._update_horizon_glow_callback:
                self._ui_helper.call(
                    lambda: self._update_horizon_glow_callback("disconnecting")
                )

        def disconnect_task():
            if self._is_running_setter:
                self._is_running_setter(False)
            if self._profile_manager_is_running_setter:
                self._profile_manager_is_running_setter(False)
            if self._monitoring_service_is_running_setter:
                self._monitoring_service_is_running_setter(False)

            # Stop network stats monitoring
            try:
                self._network_stats.stop()
                if self._logs_drawer_component and self._ui_helper:
                    self._ui_helper.call(self._logs_drawer_component.show_stats, False)
            except Exception:
                pass

            try:
                self._connection_manager.disconnect()
            except Exception:
                pass

            try:
                if self._log_viewer:
                    self._log_viewer.stop_tailing()
            except Exception:
                pass

            import time

            time.sleep(1.0)

            if self._ui_helper:
                self._ui_helper.call(self.reset_ui_disconnected)

            # Update system tray state
            if self._systray:
                self._systray.update_state()

        threading.Thread(target=disconnect_task, daemon=True).start()

    def reset_ui_disconnected(self):
        """Reset UI to disconnected state."""
        if self._is_running_setter:
            self._is_running_setter(False)
        if self._connecting_setter:
            self._connecting_setter(False)
        if self._profile_manager_is_running_setter:
            self._profile_manager_is_running_setter(False)
        if self._monitoring_service_is_running_setter:
            self._monitoring_service_is_running_setter(False)

        try:
            if self._connection_button:
                self._connection_button.set_disconnected()
            if self._status_display:
                self._status_display.set_disconnected()
            if self._update_horizon_glow_callback:
                self._update_horizon_glow_callback("disconnected")

            # Trigger immediate latency check via dedicated handler
            if self._latency_monitor_handler:
                self._latency_monitor_handler.trigger_single_check()

        except Exception as e:
            logger.debug(f"[ConnectionHandler] Error in reset_ui_disconnected: {e}")
