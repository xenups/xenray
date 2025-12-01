"""Main application entry point."""
import os
import sys

import flet as ft

# Add project root to path
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.constants import EARLY_LOG_FILE
from src.core.logger import logger
from src.core.settings import Settings
from src.ui.main_window import MainWindow


def main(page: ft.Page):
    """Main entry point."""
    
    # Setup logging
    Settings.create_temp_directories()
    Settings.create_log_files()
    Settings.setup_logging(EARLY_LOG_FILE)
    
    # Initialize Core Services
    config_manager = ConfigManager()
    connection_manager = ConnectionManager(config_manager)
    
    # Initialize UI
    window = MainWindow(
        page,
        config_manager,
        connection_manager
    )
    
    # Handle window close
    def on_window_close(e):
        logger.debug(f"[DEBUG] Window event: {e.data}")
        if e.data == "close":
            logger.debug("[DEBUG] Closing window...")
            try:
                # Cleanup resources
                window.cleanup()
                logger.debug("[DEBUG] Cleanup finished")
            except Exception as ex:
                logger.debug(f"[DEBUG] Cleanup error: {ex}")
            
            logger.debug("[DEBUG] Destroying window")
            page.window.destroy()
            logger.debug("[DEBUG] Window destroyed")
            # Force exit to ensure no hanging threads
            os._exit(0)
    
    page.window.prevent_close = True
    page.window.on_event = on_window_close

def run():
    """Entry point for poetry script."""
    ft.app(target=main)

if __name__ == "__main__":
    run()
