"""
Configuration processing service.

Handles all configuration-related operations:
- Loading and validation
- Processing (DNS resolution, SNI patching)
- Saving processed configs
"""

import json
import os
from typing import Optional

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import OUTPUT_CONFIG_PATH


class ConfigurationProcessor:
    """
    Processes and validates Xray configurations.
    
    Single Responsibility: Configuration processing only.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize configuration processor.
        
        Args:
            config_manager: Configuration manager instance
        """
        self._config_manager = config_manager
    
    def load_and_validate(self, file_path: str) -> Optional[dict]:
        """
        Load and validate configuration file.
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Configuration dict if valid, None otherwise
        """
        logger.debug(f"Loading config from {file_path}")
        config, _ = self._config_manager.load_config(file_path)
        
        if not config:
            logger.error("Failed to load config")
            return None
        
        if not isinstance(config, dict):
            logger.error(f"Invalid config format: expected dict, got {type(config).__name__}")
            return None
        
        return config
    
    def process_and_save(
        self,
        config: dict,
        process_func,
        get_socks_port_func
    ) -> tuple[Optional[dict], Optional[int]]:
        """
        Process configuration and save to output path.
        
        Args:
            config: Raw configuration
            process_func: Function to process config
            get_socks_port_func: Function to extract SOCKS port
            
        Returns:
            Tuple of (processed_config, socks_port) or (None, None) on error
        """
        logger.debug("Processing configuration")
        processed_config = process_func(config)
        socks_port = get_socks_port_func(processed_config)
        
        # Save processed config
        logger.debug(f"Saving processed config to {OUTPUT_CONFIG_PATH}")
        try:
            with open(OUTPUT_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(processed_config, f, indent=2)
            logger.debug("Config saved successfully")
        except Exception as e:
            logger.error(f"Failed to save Xray config: {e}")
            return None, None
        
        return processed_config, socks_port
