"""Config File Loader - Loads and parses Xray config files."""
import json
import os
import re
from typing import Optional, Tuple

from src.core.logger import logger


def _validate_file_path(file_path: str) -> bool:
    """Validate file path to prevent path traversal attacks."""
    if not file_path or not isinstance(file_path, str):
        return False
    normalized = os.path.normpath(file_path)
    if ".." in normalized:
        return False
    return True


class ConfigFileLoader:
    """Loads and parses Xray config files with comment stripping."""

    # Regex pattern for stripping comments while preserving strings
    _COMMENT_PATTERN = re.compile(r'("[^"\\]*(?:\\.[^"\\]*)*")|//[^\n]*|/\*[\s\S]*?\*/')

    def load(self, file_path: str) -> Tuple[Optional[dict], bool]:
        """
        Load configuration from file.

        Args:
            file_path: Path to the configuration file

        Returns:
            Tuple of (config_dict, should_remove_from_recent)
            Returns (None, True) if file doesn't exist or is invalid
        """
        if not _validate_file_path(file_path):
            logger.warning(f"Invalid file path: {file_path}")
            return None, True

        if not os.path.exists(file_path):
            return None, True

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Strip comments while preserving strings
            content = self._strip_comments(content)
            config = json.loads(content)
            return config, False

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing config file {file_path}: {e}")
            return None, True
        except (OSError, IOError) as e:
            logger.error(f"Error reading config file {file_path}: {e}")
            return None, True
        except Exception as e:
            logger.error(f"Unexpected error loading config {file_path}: {e}")
            return None, True

    def _strip_comments(self, content: str) -> str:
        """Strip // and /* */ comments while preserving quoted strings."""

        def replacer(match):
            if match.group(1):
                return match.group(1)  # Keep strings
            return ""  # Remove comments

        return self._COMMENT_PATTERN.sub(replacer, content)

    def validate(self, config: dict) -> bool:
        """Validate configuration structure."""
        if not config or not isinstance(config, dict):
            return False
        return "outbounds" in config
