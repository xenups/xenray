"""Network interface utilities for Windows."""
import subprocess
import re
from typing import Optional, Tuple
from loguru import logger


class NetworkInterfaceDetector:
    """Detects primary network interface on Windows."""
    
    @staticmethod
    def get_primary_interface() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get primary network interface details.
        
        Returns:
            Tuple of (interface_name, interface_ip, subnet)
            e.g., ("Wi-Fi", "192.168.1.10", "192.168.1.0/24")
        """
        try:
            # Get default route to find primary interface
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to get route table: {result.stderr}")
                return None, None, None
            
            # Parse route output to find default gateway
            # Looking for line like: "0.0.0.0          0.0.0.0     192.168.1.1    192.168.1.10     25"
            for line in result.stdout.split('\n'):
                if '0.0.0.0' in line and '0.0.0.0' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        gateway = parts[2]
                        interface_ip = parts[3]
                        
                        # Get interface name from IP
                        interface_name = NetworkInterfaceDetector._get_interface_name(interface_ip)
                        
                        # Calculate subnet (assume /24 for simplicity)
                        subnet = NetworkInterfaceDetector._calculate_subnet(interface_ip)
                        
                        logger.info(f"Detected primary interface: {interface_name} ({interface_ip}, {subnet})")
                        return interface_name, interface_ip, subnet
            
            logger.warning("Could not detect primary interface from route table")
            return None, None, None
            
        except Exception as e:
            logger.error(f"Error detecting primary interface: {e}")
            return None, None, None
    
    @staticmethod
    def _get_interface_name(ip: str) -> Optional[str]:
        """Get interface name from IP address using ipconfig."""
        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Parse ipconfig output
            current_adapter = None
            for line in result.stdout.split('\n'):
                # Check for adapter name
                if "adapter" in line.lower():
                    # Extract adapter name
                    match = re.search(r'adapter (.+?):', line)
                    if match:
                        current_adapter = match.group(1).strip()
                
                # Check for IPv4 address
                if "IPv4 Address" in line and ip in line:
                    return current_adapter
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting interface name: {e}")
            return None
    
    @staticmethod
    def _calculate_subnet(ip: str) -> str:
        """Calculate subnet from IP (assumes /24)."""
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return f"{ip}/32"
