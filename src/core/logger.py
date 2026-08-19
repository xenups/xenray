import os
import sys

from loguru import logger

from src.core.constants import LOG_BACKUP_COUNT, TMPDIR


def _log_filter(record: dict) -> bool:
    """Filter out UI module debug logs from console and application logs."""
    name = record.get("name") or ""
    level = record.get("level")
    level_no = getattr(level, "no", 0)
    if name.startswith("src.ui") and level_no < 30:
        return False
    return True


# Configure logger
logger.remove()  # Remove default handler

# Add stderr handler only if available (not in windowed exe)
if sys.stderr:
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(sys.stderr, format=log_format, level="DEBUG", filter=_log_filter)

# Add file handler
log_file = os.path.join(TMPDIR, "xenray.log")
os.makedirs(TMPDIR, exist_ok=True)  # Guarantee directory exists before handler creation
logger.add(
    log_file,
    # Strict rotation: rotate once the active file reaches exactly 5 MB
    # ("5 MiB" == 5 * 1024 * 1024 bytes) and retain at most 3 historical
    # rotated files so the log directory never accumulates unbounded files.
    rotation="5 MiB",
    retention=LOG_BACKUP_COUNT,
    encoding="utf-8",
    format=("{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | " "{name}:{function}:{line} - {message}"),
    level="DEBUG",
    filter=_log_filter,
)


def get_logger():
    return logger
