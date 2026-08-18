"""Settings Controller - manages settings validation, persistence, and event emissions."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.event_bus import event_bus
from src.core.i18n import t
from src.core.logger import logger


class SettingsController:
    """Controller handling settings validation, repository updates, and pub/sub notifications."""

    def __init__(self, app_context, toast_callback: Optional[Callable[[str, str], None]] = None) -> None:
        self._app_context = app_context
        self._toast_callback = toast_callback

    def _show_toast(self, message: str, message_type: str = "info", page: Optional[object] = None) -> None:
        """Dispatch a toast through exactly ONE path.

        When a toast callback is wired (the settings drawer), it is the sole
        dispatcher — it routes to ``page._toast_manager.show`` which appends to
        the overlay and dispatches ``page.update(overlay)``. The ``page``
        fallback is used only when no callback exists (standalone controller).
        Firing BOTH would render the toast twice, stacked in the wrong spot.
        """
        if self._toast_callback:
            try:
                self._toast_callback(message, message_type)
            except Exception as e:
                logger.error(f"[SettingsController] Toast callback error: {e}")
            return

        if page:
            try:
                from src.ui.components.common.toast import ToastManager

                if message_type == "success":
                    ToastManager.show_success(page, message)
                elif message_type == "error":
                    ToastManager.show_error(page, message)
                elif message_type == "warning":
                    ToastManager.show_warning(page, message)
                else:
                    ToastManager.show_info(page, message)
            except Exception as ex:
                logger.error(f"[SettingsController] ToastManager error: {ex}")

    def update_socks_port(self, val: int | str) -> tuple[bool, str]:
        """Validate and persist new SOCKS5 proxy port (1024 - 65535).

        Returns (success: bool, result_or_error: str).
        """
        try:
            port = int(val)
            if 1024 <= port <= 65535:
                if self._app_context and hasattr(self._app_context, "settings"):
                    self._app_context.settings.set_proxy_port(port)
                event_bus.publish("settings_updated", {"setting": "socks_port", "value": port})
                msg = t(
                    "settings.port_saved",
                    default=f"SOCKS Port saved: {port}",
                    port=port,
                )
                self._show_toast(msg, "success")
                return True, str(port)
            else:
                err = t(
                    "settings.port_invalid_range",
                    default="Port must be between 1024 and 65535",
                )
                self._show_toast(err, "error")
                return False, err
        except (ValueError, TypeError):
            err = t("settings.port_must_be_number", default="Port must be a valid number")
            self._show_toast(err, "error")
            return False, err

    def update_http_port(self, val: int | str) -> tuple[bool, str]:
        """Validate and persist new HTTP proxy port (1024 - 65535).

        Returns (success: bool, result_or_error: str).
        """
        try:
            port = int(val)
            if 1024 <= port <= 65535:
                if self._app_context and hasattr(self._app_context, "settings"):
                    self._app_context.settings.set_http_port(port)
                event_bus.publish("settings_updated", {"setting": "http_port", "value": port})
                msg = t(
                    "settings.http_port_saved",
                    default=f"HTTP Proxy Port saved: {port}",
                    port=port,
                )
                self._show_toast(msg, "success")
                return True, str(port)
            else:
                err = t(
                    "settings.port_invalid_range",
                    default="Port must be between 1024 and 65535",
                )
                self._show_toast(err, "error")
                return False, err
        except (ValueError, TypeError):
            err = t("settings.port_must_be_number", default="Port must be a valid number")
            self._show_toast(err, "error")
            return False, err

    def update_tun_engine(self, engine: str) -> bool:
        """Persist selected TUN engine (sing-box / xray)."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_tun_engine(engine)
            event_bus.publish("settings_updated", {"setting": "tun_engine", "value": engine})
            self._show_toast(
                t("settings.tun_engine_saved", default=f"TUN Engine set to {engine}"),
                "success",
            )
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting TUN engine: {e}")
            return False

    def update_routing_country(self, code: str) -> bool:
        """Persist selected routing country code, emit events, and show feedback toast."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                if hasattr(self._app_context.settings, "set_routing_country"):
                    self._app_context.settings.set_routing_country(code)
                if hasattr(self._app_context.settings, "set_direct_country"):
                    self._app_context.settings.set_direct_country(code)

            event_bus.publish("settings_updated", {"setting": "routing_country", "value": code})
            event_bus.publish("routing_rules_updated", {"setting": "routing_country", "value": code})

            code_display = (code or "NONE").upper()
            msg = t(
                "settings.country_saved",
                default=f"Direct Country updated: {code_display}",
                country=code_display,
                val=code_display,
            )
            self._show_toast(msg, "success")
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting routing country: {e}")
            err = t(
                "settings.country_save_error",
                default="Error updating Direct Country settings",
            )
            self._show_toast(err, "error")
            return False

    def update_language(self, code: str) -> bool:
        """Persist selected UI language code and show feedback toast."""
        try:
            from src.core.i18n import set_language

            set_language(code)
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_language(code)
            event_bus.publish("settings_updated", {"setting": "language", "value": code})
            msg = t(
                "settings.language_saved",
                default=f"Language set to {code.upper()}",
                code=code.upper(),
            )
            self._show_toast(msg, "success")
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting language: {e}")
            err = t(
                "settings.language_save_error",
                default="Error updating language setting",
            )
            self._show_toast(err, "error")
            return False

    def update_auto_reconnect(self, enabled: bool) -> bool:
        """Persist auto-reconnect preference and trigger toast feedback."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_auto_reconnect_enabled(enabled)
            event_bus.publish("settings_updated", {"setting": "auto_reconnect", "value": enabled})
            msg = t("settings.auto_reconnect_enabled") if enabled else t("settings.auto_reconnect_disabled")
            self._show_toast(msg, "success" if enabled else "info")
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting auto-reconnect: {e}")
            self._show_toast(t("settings.update_error", default="Error updating settings"), "error")
            return False

    def update_lan_sharing(self, enabled: bool) -> bool:
        """Persist LAN proxy sharing setting and trigger toast feedback."""
        try:
            from src.ui.controllers.lan_sharing_controller import LanSharingController

            controller = LanSharingController(app_context=self._app_context)
            controller.set_lan_sharing_enabled(enabled)
            msg = t("settings.lan_enabled") if enabled else t("settings.lan_disabled")
            self._show_toast(msg, "success" if enabled else "info")
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting LAN sharing: {e}")
            self._show_toast(t("settings.update_error", default="Error updating settings"), "error")
            return False

    def update_startup(self, enabled: bool, on_register: Callable, on_unregister: Callable) -> bool:
        """Handle OS startup task registration and trigger feedback toast."""
        try:
            if enabled:
                success, _ = on_register()
            else:
                success, _ = on_unregister()

            if success:
                if self._app_context and hasattr(self._app_context, "settings"):
                    self._app_context.settings.set_startup_enabled(enabled)
                event_bus.publish("settings_updated", {"setting": "startup", "value": enabled})
                self._show_toast(t("settings.startup_saved"), "success")
                return True
            else:
                self._show_toast(t("settings.startup_error"), "error")
                return False
        except Exception as e:
            logger.error(f"[SettingsController] Error setting startup preference: {e}")
            self._show_toast(t("settings.startup_error"), "error")
            return False

    def check_for_updates(
        self,
        update_card_ref: Optional[object] = None,
        page_ref: Optional[object] = None,
        sync: bool = False,
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """Check for application updates via AppUpdateService and provide UI toast/dialog feedback."""
        if update_card_ref and hasattr(update_card_ref, "set_checking"):
            update_card_ref.set_checking(True)

        def _do_check():
            try:
                from src.services.app_update_service import AppUpdateService

                update_avail, current_ver, latest_ver, download_url = AppUpdateService.check_for_updates()

                if latest_ver is None:
                    err_msg = t(
                        "settings.update_check_failed",
                        default="Failed to check for updates",
                    )
                    self._show_toast(err_msg, "error", page=page_ref)
                elif update_avail:
                    msg = t(
                        "settings.update_available",
                        default=f"New version {latest_ver} available!",
                        version=latest_ver,
                    )
                    self._show_toast(msg, "success", page=page_ref)
                    if page_ref and hasattr(page_ref, "show_dialog"):
                        self._show_update_dialog(
                            page_ref,
                            current_ver,
                            latest_ver,
                            download_url,
                            update_card_ref,
                        )
                else:
                    msg = t("settings.up_to_date", default="XenRay is up to date")
                    self._show_toast(msg, "success", page=page_ref)

                return update_avail, current_ver, latest_ver, download_url
            except Exception as e:
                logger.error(f"[SettingsController] Error checking for updates: {e}")
                err_msg = t(
                    "settings.update_check_failed",
                    default="Failed to check for updates",
                )
                self._show_toast(err_msg, "error", page=page_ref)
                return False, "0.3.0-beta", None, None
            finally:
                if update_card_ref and hasattr(update_card_ref, "set_checking"):
                    update_card_ref.set_checking(False)

        if sync:
            return _do_check()
        else:
            import threading

            threading.Thread(target=_do_check, daemon=True).start()
            return False, None, None, None

    def _show_update_dialog(
        self,
        page,
        current: str,
        latest: str,
        download_url: Optional[str],
        update_card_ref: Optional[object] = None,
    ):
        """Show the interactive UpdateDialog (live progress, result toasts)."""
        if not page:
            return

        from src.ui.components.dialogs.update_dialog import UpdateDialog

        def close_dlg(e):
            try:
                page.pop_dialog()
            except Exception:
                pass

        def start_update(e):
            if not download_url:
                self._show_toast(
                    t("settings.download_failed", default="Failed to download update"),
                    "error",
                    page=page,
                )
                return

            import threading

            from src.services.app_update_service import AppUpdateService

            dlg.set_status(t("settings.downloading_update", default="Downloading update..."))

            def update_worker():
                if update_card_ref and hasattr(update_card_ref, "set_checking"):
                    update_card_ref.set_checking(True)
                try:

                    def on_progress(p):
                        dlg.set_progress(p / 100.0)
                        dlg.set_status(f"{t('settings.downloading_update', default='Downloading update...')} {p}%")

                    zip_path = AppUpdateService.download_update(download_url, on_progress)
                    if zip_path:
                        dlg.set_status(t("settings.applying_update", default="Applying update..."))
                        if AppUpdateService.apply_update(zip_path):
                            dlg.set_status(t("app_update.restarting", default="Restarting..."))
                            self._show_toast(
                                t(
                                    "settings.update_applied",
                                    default="Update applied successfully",
                                ),
                                "success",
                                page=page,
                            )
                        else:
                            self._show_toast(
                                t(
                                    "settings.download_failed",
                                    default="Failed to apply update",
                                ),
                                "error",
                                page=page,
                            )
                    else:
                        self._show_toast(
                            t(
                                "settings.download_failed",
                                default="Failed to download update",
                            ),
                            "error",
                            page=page,
                        )
                except Exception as ex:
                    logger.error(f"[SettingsController] App update download error: {ex}")
                    self._show_toast(
                        t(
                            "settings.download_failed",
                            default="Failed to download update",
                        ),
                        "error",
                        page=page,
                    )
                finally:
                    if update_card_ref and hasattr(update_card_ref, "set_checking"):
                        update_card_ref.set_checking(False)

            threading.Thread(target=update_worker, daemon=True).start()

        dlg = UpdateDialog(
            current_version=current or "?",
            latest_version=latest,
            release_notes="",
            on_update_now=start_update,
            on_cancel=close_dlg,
            on_remind_later=close_dlg,
            title_text=t("app_update.title", default="Update Available"),
        )
        try:
            page.show_dialog(dlg)
        except Exception as ex:
            logger.error(f"[SettingsController] Failed to show update dialog: {ex}")

    def check_xray_core_update(
        self,
        core_card_ref: Optional[object] = None,
        page_ref: Optional[object] = None,
        sync: bool = False,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check for Xray-Core binary updates from GitHub releases.

        Returns (update_available: bool, current_version: str|None, latest_version: str|None).
        """
        if core_card_ref and hasattr(core_card_ref, "set_checking"):
            core_card_ref.set_checking(True)

        def _do_check():
            try:
                from src.services.xray_installer import XrayInstallerService

                try:
                    available, current_ver, latest_ver = XrayInstallerService.check_for_updates(include_prerelease=True)
                except TypeError:
                    available, current_ver, latest_ver = XrayInstallerService.check_for_updates()

                if latest_ver is None:
                    err_msg = t(
                        "settings.xray_core_check_failed",
                        default="Failed to check Xray-Core update",
                    )
                    self._show_toast(err_msg, "error", page=page_ref)
                elif available:
                    msg = t(
                        "settings.xray_core_update_available",
                        default=f"Xray-Core v{latest_ver} available!",
                        version=latest_ver,
                    )
                    self._show_toast(msg, "success", page=page_ref)
                    if page_ref and hasattr(page_ref, "show_dialog"):
                        self._show_xray_core_update_dialog(page_ref, current_ver, latest_ver, core_card_ref)
                else:
                    msg = t(
                        "settings.xray_core_up_to_date",
                        default="Xray-Core is up to date",
                    )
                    self._show_toast(msg, "success", page=page_ref)

                return available, current_ver, latest_ver
            except Exception as e:
                logger.error(f"[SettingsController] Error checking for Xray-Core update: {e}")
                err_msg = t(
                    "settings.xray_core_check_failed",
                    default="Failed to check Xray-Core update",
                )
                self._show_toast(err_msg, "error", page=page_ref)
                return False, None, None
            finally:
                if core_card_ref and hasattr(core_card_ref, "set_checking"):
                    core_card_ref.set_checking(False)

        if sync:
            return _do_check()
        else:
            import threading

            threading.Thread(target=_do_check, daemon=True).start()
            return False, None, None

    def _show_xray_core_update_dialog(
        self,
        page,
        current: Optional[str],
        latest: str,
        core_card_ref: Optional[object] = None,
    ):
        """Show Xray-Core update confirmation modal dialog."""
        if not page:
            return

        def close_dlg(e):
            try:
                page.pop_dialog()
            except Exception:
                pass

        def start_core_install(e):
            try:
                page.pop_dialog()
            except Exception:
                pass

            import threading

            from src.services.xray_installer import XrayInstallerService

            msg = t(
                "settings.updating_xray_core",
                default="Downloading and replacing Xray-Core...",
            )
            self._show_toast(msg, "info", page=page)

            def install_worker():
                if core_card_ref and hasattr(core_card_ref, "set_checking"):
                    core_card_ref.set_checking(True)
                try:
                    success = XrayInstallerService.install(target_version=latest)
                    if success:
                        ok_msg = t(
                            "settings.xray_core_updated",
                            default="Xray-Core updated successfully",
                        )
                        self._show_toast(ok_msg, "success", page=page)
                        if core_card_ref and hasattr(core_card_ref, "refresh_version"):
                            core_card_ref.refresh_version()
                    else:
                        err_msg = t(
                            "settings.xray_core_update_failed",
                            default="Failed to update Xray-Core",
                        )
                        self._show_toast(err_msg, "error", page=page)
                except Exception as ex:
                    logger.error(f"[SettingsController] Xray-Core installation error: {ex}")
                    err_msg = t(
                        "settings.xray_core_update_failed",
                        default="Failed to update Xray-Core",
                    )
                    self._show_toast(err_msg, "error", page=page)
                finally:
                    if core_card_ref and hasattr(core_card_ref, "set_checking"):
                        core_card_ref.set_checking(False)

            threading.Thread(target=install_worker, daemon=True).start()

        curr_str = current or "N/A"
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("settings.xray_core_update_title", default="Xray-Core Update")),
            content=ft.Column(
                [
                    ft.Text(f"Current: v{curr_str} → Latest: v{latest}"),
                    ft.Text(
                        t(
                            "settings.xray_core_update_message",
                            default="Are you sure you want to download and update Xray-Core?",
                        ),
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton(t("common.cancel", default="Cancel"), on_click=close_dlg),
                ft.TextButton(
                    t("common.install", default="Install & Update"),
                    on_click=start_core_install,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        try:
            page.show_dialog(dlg)
        except Exception as ex:
            logger.error(f"[SettingsController] Failed to show Xray-Core update dialog: {ex}")
