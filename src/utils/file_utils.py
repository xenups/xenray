"""File operation utilities."""
import json
import os
from typing import Optional

from src.core.logger import logger


class FileUtils:
    """Utility class for file operations."""
    
    @staticmethod
    def read_json(file_path: str) -> Optional[dict]:
        """
        Read JSON from file.
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            Dictionary or None if read fails
        """
        if not file_path or not isinstance(file_path, str):
            logger.warning("Invalid file path provided")
            return None
        
        if not os.path.exists(file_path):
            logger.debug(f"File does not exist: {file_path}")
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse JSON from {file_path}: {e}")
            return None
        except (OSError, IOError) as e:
            logger.error(f"Failed to read JSON from {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading JSON from {file_path}: {e}")
            return None
    
    @staticmethod
    def write_json(file_path: str, data: dict, indent: int = 2) -> bool:
        """
        Write JSON to file.
        
        Args:
            file_path: Path to write to
            data: Dictionary to write
            indent: JSON indentation
            
        Returns:
            True if successful, False otherwise
        """
        if not file_path or not isinstance(file_path, str):
            logger.warning("Invalid file path provided")
            return False
        
        if not isinstance(data, dict):
            logger.warning("Data must be a dictionary")
            return False
        
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            return True
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON to {file_path}: {e}")
            return False
        except (OSError, IOError) as e:
            logger.error(f"Failed to write JSON to {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error writing JSON to {file_path}: {e}")
            return False
    
    @staticmethod
    def read_text(file_path: str) -> Optional[str]:
        """
        Read text from file.
        
        Args:
            file_path: Path to text file
            
        Returns:
            File contents or None if read fails
        """
        if not file_path or not isinstance(file_path, str):
            logger.warning("Invalid file path provided")
            return None
        
        if not os.path.exists(file_path):
            logger.debug(f"File does not exist: {file_path}")
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except (UnicodeDecodeError, UnicodeError) as e:
            logger.error(f"Failed to decode text from {file_path}: {e}")
            return None
        except (OSError, IOError) as e:
            logger.error(f"Failed to read text from {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading text from {file_path}: {e}")
            return None
    
    @staticmethod
    def write_text(file_path: str, content: str) -> bool:
        """
        Write text to file.
        
        Args:
            file_path: Path to write to
            content: Text content
            
        Returns:
            True if successful, False otherwise
        """
        if not file_path or not isinstance(file_path, str):
            logger.warning("Invalid file path provided")
            return False
        
        if not isinstance(content, str):
            logger.warning("Content must be a string")
            return False
        
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except (OSError, IOError) as e:
            logger.error(f"Failed to write text to {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error writing text to {file_path}: {e}")
            return False
    
    @staticmethod
    def ensure_directory(directory: str) -> None:
        """
        Ensure directory exists.
        
        Args:
            directory: Directory path
        """
        if not directory or not isinstance(directory, str):
            logger.warning("Invalid directory path provided")
            return
        
        try:
            os.makedirs(directory, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            raise
