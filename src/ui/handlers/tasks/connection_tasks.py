"""Connection Tasks - Outbound public IP lookups and background thread tasks."""

from __future__ import annotations

from typing import Callable, Optional

from src.core.logger import logger
from src.services.ip_geolocation_service import fetch_public_exit_ip


class ConnectionTasks:
    """Task handlers for async location IP fetching and connection management."""

    @staticmethod
    def fetch_location_ip_task(
        proxy_port: int,
        profile: dict,
        get_main_window_fn: Callable,
        ui_call_fn: Callable,
    ):
        """Fetch public location exit IP through connected tunnel."""
        try:
            exit_ip, code, name = fetch_public_exit_ip(proxy_port)
            mw = get_main_window_fn()
            if exit_ip:
                profile["exit_ip"] = exit_ip
                if code:
                    profile["country_code"] = code
                if name:
                    profile["country_name"] = name

                if mw:
                    mw._current_exit_ip = exit_ip
                    if hasattr(mw, "_update_selected_profile_ui"):
                        ui_call_fn(lambda: mw._update_selected_profile_ui(profile))
            else:
                if mw:
                    ui_call_fn(lambda: setattr(mw, "_current_exit_ip", None))
        except Exception as e:
            logger.debug(f"[ConnectionTasks] Location IP fetch failed: {e}")
            mw = get_main_window_fn()
            if mw:
                ui_call_fn(lambda: setattr(mw, "_current_exit_ip", None))
