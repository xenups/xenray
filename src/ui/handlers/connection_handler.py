"""Connection Handler - Manages connection lifecycle."""
from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING

from src.core.constants import SINGBOX_LOG_FILE, TMPDIR, XRAY_LOG_FILE
from src.core.logger import logger
from src.core.types import ConnectionMode

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class ConnectionHandler:
    """Handles connection lifecycle (connect, disconnect, reconnect)."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def connect_async(self):
        """Start connection in background thread."""
        if self._main._connecting:
            return
        self._main._connecting = True

        # Show connecting animation immediately
        self._main._ui_call(self._main._connection_button.set_connecting)
        self._main._ui_call(self._main._status_display.set_initializing)
        self._main._ui_call(lambda: self._main._update_horizon_glow("connecting"))

        threading.Thread(target=self._perform_connect_task, daemon=True).start()

    def reconnect(self):
        """Fast reconnect for server switching while running."""
        if self._main._connecting:
            return

        self._main._connecting = True

        # Visually switch to "Connecting" (Amber) immediately
        # We DON'T show Disconnecting (Red) or Disconnected (Orange)
        self._main._ui_call(self._main._connection_button.set_connecting)
        self._main._ui_call(self._main._status_display.set_initializing)
        self._main._ui_call(lambda: self._main._update_horizon_glow("connecting"))

        def fast_reconnect_task():
            try:
                # 1. Kill current connection silently (no delays, no UI reset)
                self._main._is_running = False
                try:
                    self._main._connection_manager.disconnect()
                except Exception:
                    pass

                # 2. Immediately start new connection
                self._perform_connect_task()
            except Exception as e:
                logger.error(f"Error in fast_reconnect_task: {e}")
                self._main._connecting = False
                self._main._ui_call(self.reset_ui_disconnected)

        threading.Thread(target=fast_reconnect_task, daemon=True).start()

    def _perform_connect_task(self):
        """Core connection logic reused by connect_async and reconnect."""
        try:
            # Check Internet Connectivity (in background thread)
            from src.utils.network_utils import NetworkUtils

            if not NetworkUtils.check_internet_connection():
                self._main._connecting = False
                self._main._ui_call(self.reset_ui_disconnected)
                self._main._toast.error("No Internet Connection", 3000)
                return

            profile_config = (
                self._main._selected_profile.get("config")
                if self._main._selected_profile
                else {}
            )
            mode_str = (
                "vpn" if self._main._current_mode == ConnectionMode.VPN else "proxy"
            )

            os.makedirs(TMPDIR, exist_ok=True)

            # Start logging
            app_log = os.path.join(TMPDIR, "xenray.log")
            if self._main._current_mode == ConnectionMode.VPN:
                self._main._log_viewer.start_tailing(
                    app_log, XRAY_LOG_FILE, SINGBOX_LOG_FILE
                )
            else:
                self._main._log_viewer.start_tailing(app_log, XRAY_LOG_FILE)

            temp_config_path = os.path.join(TMPDIR, "current_config.json")
            with open(temp_config_path, "w", encoding="utf-8") as f:
                json.dump(profile_config, f)

            def on_step(step_msg: str):
                self._main._ui_call(self._main._status_display.set_step, step_msg)

            success = self._main._connection_manager.connect(
                temp_config_path, mode_str, step_callback=on_step
            )

            if not success:
                self._main._connecting = False
                self._main._ui_call(self.reset_ui_disconnected)
                self._main._toast.error("Connection Failed", 3000)
                return

            self._main._is_running = True

            # --- Post-Connection Internet Check ---
            # Wait a brief moment for core to stabilize
            import time

            time.sleep(1)

            self._main._ui_call(
                self._main._status_display.set_step, "Verifying Internet Access..."
            )

            proxy_port = self._main._config_manager.get_proxy_port()
            if not NetworkUtils.check_proxy_connectivity(proxy_port):
                logger.error("Post-connection internet check failed")
                self._main._connecting = False
                # Use disconnect to cleanup
                self._main._connection_manager.disconnect()
                self._main._ui_call(self.reset_ui_disconnected)
                self._main._toast.warning("Connected but No Internet Access", 3000)
                return
            # --------------------------------------

            self._main._connecting = False

            self._main._ui_call(
                self._main._status_display.set_connected,
                country_data=self._main._selected_profile,
            )
            self._main._ui_call(self._main._connection_button.set_connected)
            self._main._ui_call(lambda: self._main._update_horizon_glow("connected"))

            # Update system tray state
            self._main._systray.update_state()

            # Start network stats service
            if self._main._network_stats:
                self._main._network_stats.start()
                if self._main._logs_drawer_component:
                    self._main._ui_call(
                        self._main._logs_drawer_component.show_stats, True
                    )

        except Exception as e:
            logger.error(f"Error in _perform_connect_task: {e}")
            self._main._connecting = False
            self._main._ui_call(self.reset_ui_disconnected)

    def disconnect(self):
        """Disconnect from VPN/Proxy."""
        if not self._main._is_running:
            return

        # Show disconnecting UI immediately
        self._main._ui_call(self._main._connection_button.set_disconnecting)
        self._main._ui_call(self._main._status_display.set_disconnecting)
        self._main._ui_call(lambda: self._main._update_horizon_glow("disconnecting"))

        def disconnect_task():
            self._main._is_running = False

            # Stop network stats monitoring
            try:
                self._main._network_stats.stop()
                if self._main._logs_drawer_component:
                    self._main._ui_call(
                        self._main._logs_drawer_component.show_stats, False
                    )
            except Exception:
                pass

            try:
                self._main._connection_manager.disconnect()
            except Exception:
                pass

            try:
                self._main._log_viewer.stop_tailing()
            except Exception:
                pass

            # Small delay to let user see disconnecting state
            import time

            time.sleep(1.0)

            self._main._ui_call(self.reset_ui_disconnected)

            # Update system tray state
            self._main._systray.update_state()

        threading.Thread(target=disconnect_task, daemon=True).start()

    def reset_ui_disconnected(self):
        """Reset UI to disconnected state."""
        self._main._is_running = False
        self._main._connecting = False
        try:
            self._main._connection_button.set_disconnected()
            self._main._status_display.set_disconnected()
            self._main._update_horizon_glow("disconnected")

            # Trigger immediate latency check
            if self._main._selected_profile:
                profile_name = self._main._selected_profile.get("name")
                logger.debug(
                    f"[ConnectionHandler] Starting post-disconnection ping test for: {profile_name}"
                )
                self._main._ui_call(
                    self._main._status_display.set_pre_connection_ping, "...", False
                )

                def on_result(success, result_str, country_data=None):
                    logger.debug(
                        f"[ConnectionHandler] Ping result received: {result_str} (success={success})"
                    )

                    # More relaxed guard: only skip if we started CONNECTING again
                    if not self._main._connecting:
                        self._main._ui_call(
                            self._main._status_display.set_pre_connection_ping,
                            result_str,
                            success,
                        )
                        # Update country if found
                        if country_data and self._main._selected_profile:
                            self._main._selected_profile.update(country_data)
                            self._main._config_manager.update_profile(
                                self._main._selected_profile.get("id"), country_data
                            )
                            # Removed: self._main._ui_call(self._main._status_display.update_country, country_data)
                    else:
                        logger.debug(
                            "[ConnectionHandler] Skipping ping update: Connection in progress"
                        )

                from src.services.connection_tester import ConnectionTester

                fetch_flag = not self._main._selected_profile.get("country_code")
                ConnectionTester.test_connection(
                    self._main._selected_profile.get("config", {}),
                    on_result,
                    fetch_country=fetch_flag,
                )

        except Exception:
            pass
