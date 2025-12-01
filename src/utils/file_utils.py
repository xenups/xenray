"""File operation utilities."""
import json
import os
from typing import Optional


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
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to read JSON from {file_path}: {e}")
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
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=indent)
            return True
        except Exception as e:
            print(f"Failed to write JSON to {file_path}: {e}")
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
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except Exception as e:
            print(f"Failed to read text from {file_path}: {e}")
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
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Failed to write text to {file_path}: {e}")
            return False
    
    @staticmethod
    def ensure_directory(directory: str) -> None:
        """
        Ensure directory exists.
        
        Args:
            directory: Directory path
        """
        os.makedirs(directory, exist_ok=True)
