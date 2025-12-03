"""Geo files installer service."""
import os
import urllib.request
import ssl
from src.core.constants import ASSETS_DIR

class GeoInstallerService:
    """Service to download and update geoip.dat and geosite.dat."""
    
    GEOIP_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geoip.dat"
    GEOSITE_URL = "https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geosite.dat"
    
    @staticmethod
    def install(progress_callback=None):
        """
        Download geo files.
        
        Args:
            progress_callback: Function to call with status updates (str)
        """
        os.makedirs(ASSETS_DIR, exist_ok=True)
        
        # Create unverified context to avoid SSL errors on some systems
        ssl_context = ssl._create_unverified_context()
        
        files = [
            ("geoip.dat", GeoInstallerService.GEOIP_URL),
            ("geosite.dat", GeoInstallerService.GEOSITE_URL)
        ]
        
        for filename, url in files:
            target_path = os.path.join(ASSETS_DIR, filename)
            if progress_callback:
                progress_callback(f"Downloading {filename}...")
                
            try:
                with urllib.request.urlopen(url, context=ssl_context) as response, open(target_path, 'wb') as out_file:
                    data = response.read()
                    out_file.write(data)
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Failed to download {filename}: {e}")
                raise e
                
        if progress_callback:
            progress_callback("Geo files updated successfully!")
