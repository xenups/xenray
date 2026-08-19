"""Log rotation, truncation, and cleanup utilities."""

from __future__ import annotations

import os

from src.core.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES, TMPDIR
from src.core.logger import logger


def truncate_log_file_inplace(
    log_file: str,
    max_bytes: int = LOG_MAX_BYTES,
    keep_bytes: int = 512 * 1024,
) -> bool:
    """Truncate a log file in-place, retaining the last ``keep_bytes`` of lines.

    Safe for Windows even when an active subprocess holds a write lock on the file.
    """
    if not os.path.exists(log_file):
        return False
    try:
        size = os.path.getsize(log_file)
        if size < max_bytes:
            return False

        logger.info(f"[LogUtils] In-place truncating oversized log ({size} bytes >= {max_bytes}): {log_file}")
        with open(log_file, "r+", encoding="utf-8", errors="ignore") as f:
            f.seek(0, os.SEEK_END)
            curr_size = f.tell()
            if curr_size < max_bytes:
                return False

            read_pos = max(0, curr_size - keep_bytes)
            f.seek(read_pos)
            if read_pos > 0:
                f.readline()  # Skip incomplete partial line

            tail_content = f.read()
            f.seek(0)
            f.write("[... Log truncated at 5 MB ceiling ...]\n" + tail_content)
            f.truncate()
            f.flush()
        return True
    except Exception as e:
        logger.warning(f"[LogUtils] In-place log truncation failed for {log_file}: {e}")
        return False


def cleanup_tmp_log_dir(max_bytes: int = LOG_MAX_BYTES) -> None:
    """Scan TMPDIR and remove all legacy log backups and truncate any oversized active logs."""
    if not os.path.exists(TMPDIR):
        return

    try:
        for file_name in os.listdir(TMPDIR):
            file_path = os.path.join(TMPDIR, file_name)
            if not os.path.isfile(file_path):
                continue
            try:
                # 1. Unconditionally purge old rotated backup files (.1, .2, .3, .old, .bak)
                if file_name.endswith((".1", ".2", ".3", ".old", ".bak")) or ".log." in file_name:
                    try:
                        os.remove(file_path)
                        logger.info(f"[LogUtils] Deleted old rotated log backup: {file_name}")
                    except OSError:
                        pass
                    continue

                # 2. Truncate any active log file exceeding max_bytes (5 MB)
                size = os.path.getsize(file_path)
                if size >= max_bytes:
                    truncate_log_file_inplace(file_path, max_bytes=max_bytes, keep_bytes=64 * 1024)
            except OSError:
                pass
    except Exception as e:
        logger.debug(f"[LogUtils] Error during temp log directory cleanup: {e}")


def purge_all_logs_on_connect() -> None:
    """Clear/truncate all *.log files and purge backup files in TMPDIR on new connection.

    Ensures every new connection starts with a fresh, clean log file.
    """
    if not os.path.exists(TMPDIR):
        return

    logger.info("[LogUtils] Clearing all log files on new connection attempt...")
    try:
        for file_name in os.listdir(TMPDIR):
            file_path = os.path.join(TMPDIR, file_name)
            if not os.path.isfile(file_path):
                continue
            try:
                # 1. Unconditionally remove rotated backup files (.1, .2, .3, .old, .bak)
                if file_name.endswith((".1", ".2", ".3", ".old", ".bak")) or ".log." in file_name:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    continue

                # 2. Clear/truncate all *.log files
                if file_name.endswith(".log"):
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write("[... Log cleared on new connection start ...]\n")
                            f.flush()
                    except OSError:
                        # Fallback if locked by open handle
                        truncate_log_file_inplace(file_path, max_bytes=0, keep_bytes=0)
            except OSError:
                pass
    except Exception as e:
        logger.debug(f"[LogUtils] Error clearing log files on connect: {e}")


def rotate_oversized_log_file(
    log_file: str,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    """Rotate a log file if it exceeds ``max_bytes``.

    If file renaming fails (e.g. Windows file lock by running subprocess),
    falls back to safe in-place tail truncation so the log file never exceeds 5 MB.
    """
    if not os.path.exists(log_file):
        return
    try:
        size = os.path.getsize(log_file)
    except OSError:
        return
    if size < max_bytes:
        return

    logger.info(f"[LogUtils] Rotating oversized log ({size} bytes >= {max_bytes}): {log_file}")

    # Drop oldest backup.
    oldest = f"{log_file}.{backup_count}"
    if os.path.exists(oldest):
        try:
            os.remove(oldest)
        except OSError:
            pass

    # Shift backups down: .N-1 -> .N, ..., .1 -> .2.
    for i in range(backup_count - 1, 0, -1):
        src = f"{log_file}.{i}"
        dst = f"{log_file}.{i + 1}"
        if os.path.exists(src):
            try:
                # If backup file itself is oversized, purge it instead of shifting
                if os.path.exists(src) and os.path.getsize(src) >= max_bytes:
                    os.remove(src)
                else:
                    os.replace(src, dst)
            except OSError:
                pass

    # Try moving current file to .1 and starting a fresh file
    try:
        os.replace(log_file, f"{log_file}.1")
        with open(log_file, "w", encoding="utf-8"):
            pass
    except OSError:
        # Windows file lock by running subprocess — fallback to in-place tail truncation!
        truncate_log_file_inplace(log_file, max_bytes=max_bytes)


__all__ = [
    "truncate_log_file_inplace",
    "cleanup_tmp_log_dir",
    "purge_all_logs_on_connect",
    "rotate_oversized_log_file",
]
