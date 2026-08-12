"""File utilities for atomic writes and JSON operations."""

import json
import os
import threading

from src.core.logger import logger

# Serializes atomic writes across threads (ping workers run via asyncio.to_thread,
# so concurrent completion tasks could otherwise collide on the same `.tmp`
# handle on Windows -> PermissionError [Errno 13]).
_write_lock = threading.Lock()


def atomic_write(file_path: str, content: str, mode: str = "w") -> bool:
    """
    Atomically write to a file to prevent corruption.

    Uses a temporary file and rename operation. A module-level thread lock
    guarantees that concurrent writers (e.g. batch inspection completions) queue
    up sequentially instead of racing on the same `.tmp` path.
    """
    with _write_lock:
        temp_path = file_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(temp_path, mode, encoding="utf-8") as f:
                f.write(content)
            if os.name == "nt":
                os.replace(temp_path, file_path)
            else:
                os.rename(temp_path, file_path)
            return True
        except (OSError, IOError) as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False


def atomic_write_json(file_path: str, data) -> bool:
    """Atomically write JSON data to a file."""
    try:
        content = json.dumps(data, indent=2)
        return atomic_write(file_path, content)
    except (TypeError, ValueError) as e:
        logger.error(f"Failed to serialize JSON for {file_path}: {e}")
        return False


def load_json_file(file_path: str, default=None):
    """Load JSON from file with error handling."""
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return default
