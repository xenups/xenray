"""Desktop OS notification helper."""

import os
import subprocess

from loguru import logger


def send_os_notification(title: str, message: str):
    """
    Log notification message. In-app notifications are displayed via Flet Toast.
    """
    logger.info(f"[Notification] {title}: {message}")
