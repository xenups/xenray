import requests
from src.core.logger import logger

class GeoIPService:
    @staticmethod
    def get_country():
        """
        Fetches the current IP's country code.
        Returns: 2-letter country code (e.g., 'US', 'DE') or None if failed.
        """
        try:
import requests
from src.core.logger import logger

class GeoIPService:
    @staticmethod
    def get_country():
        """
        Fetches the current IP's country code.
        Returns: 2-letter country code (e.g., 'US', 'DE') or None if failed.
        """
        try:
            logger.debug("[GeoIP] Requesting country from http://ip-api.com/json")
            # simple and reliable free API
            response = requests.get("http://ip-api.com/json", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"[GeoIP] Response: {data}")
                if data.get("status") == "success":
                    country_data = {
                        "country_code": data.get("countryCode"),
                        "country_name": data.get("country"),
                        "city": data.get("city")
                    }
                    logger.debug(f"[GeoIP] Found: {country_data.get('country_code')} - {country_data.get('country_name')}")
                    return country_data
        except Exception as e:
            logger.error(f"[GeoIP] Failed to fetch country: {e}")
        return None
