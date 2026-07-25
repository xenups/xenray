"""Desktop OS notification helper."""

import os
import subprocess

from loguru import logger


def send_os_notification(title: str, message: str):
    """
    Emit a native desktop OS notification.

    Args:
        title: Notification title
        message: Notification body
    """
    try:
        if os.name == "nt":
            ps_script = (
                f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms');"
                f"[reflection.assembly]::loadwithpartialname('System.Drawing');"
                f"$notify = new-object system.windows.forms.notifyicon;"
                f"$notify.icon = [system.drawing.systemicons]::Error;"
                f"$notify.visible = $true;"
                f"$notify.showballoontip(5000, '{title}', '{message}', [system.windows.forms.tooltipicon]::Error);"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            logger.info(f"[OSNotification] Sent Windows balloon notification: {title} - {message}")
        elif os.uname().sysname == "Darwin":
            cmd = f'display notification "{message}" with title "{title}"'
            subprocess.Popen(["osascript", "-e", cmd])
            logger.info(f"[OSNotification] Sent macOS notification: {title} - {message}")
        else:
            subprocess.Popen(["notify-send", title, message])
            logger.info(f"[OSNotification] Sent Linux notification: {title} - {message}")
    except Exception as e:
        logger.warning(f"[OSNotification] Failed to send OS notification: {e}")
