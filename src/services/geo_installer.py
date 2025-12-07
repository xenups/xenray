"""Geo files installer service."""
import os
import urllib.request
import ssl
from typing import Optional, Callable
from loguru import logger

from src.core.constants import ASSETS_DIR

# Constants
DOWNLOAD_TIMEOUT = 30.0  # seconds
MIN_FILE_SIZE = 1024  # bytes - minimum expected file size


class GeoInstallerService:
    """Service to download and update geoip.dat and geosite.dat."""
    
    GEOIP_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geoip.dat"
    GEOSITE_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geosite.dat"
    
    @staticmethod
    def install(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Download geo files.
        
        Args:
            progress_callback: Function to call with status updates (str)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            
            # Create SSL context with certificate verification
            # Note: Using default context instead of unverified for security
            ssl_context = ssl.create_default_context()
            
            files = [
                ("geoip.dat", GeoInstallerService.GEOIP_URL),
                ("geosite.dat", GeoInstallerService.GEOSITE_URL)
            ]
            
            for filename, url in files:
                target_path = os.path.join(ASSETS_DIR, filename)
                if progress_callback:
                    progress_callback(f"Downloading {filename}...")
                    
                try:
                    # Create request with timeout
                    request = urllib.request.Request(url)
                    with urllib.request.urlopen(request, context=ssl_context, timeout=DOWNLOAD_TIMEOUT) as response:
                        # Validate content length if available
                        content_length = response.headers.get('Content-Length')
                        if content_length and int(content_length) < MIN_FILE_SIZE:
                            logger.error(f"File {filename} too small: {content_length} bytes")
                            return False
                        
                        # Use atomic write
                        temp_path = target_path + ".tmp"
                        with open(temp_path, 'wb') as out_file:
                            data = response.read()
                            if len(data) < MIN_FILE_SIZE:
                                logger.error(f"Downloaded {filename} too small: {len(data)} bytes")
                                try:
                                    os.remove(temp_path)
                                except OSError:
                                    pass
                                return False
                            out_file.write(data)
                        
                        # Atomic rename
                        if os.name == "nt":
                            os.replace(temp_path, target_path)
                        else:
                            os.rename(temp_path, target_path)
                            
                except (urllib.error.URLError, urllib.error.HTTPError, OSError, IOError, ssl.SSLError) as e:
                    logger.error(f"Failed to download {filename}: {e}")
                    if progress_callback:
                        progress_callback(f"Failed to download {filename}: {e}")
                    return False
                    
            if progress_callback:
                progress_callback("Geo files updated successfully!")
            return True
        except Exception as e:
            logger.error(f"Geo installer failed: {e}")
            if progress_callback:
                progress_callback(f"Installation failed: {e}")
            return False
