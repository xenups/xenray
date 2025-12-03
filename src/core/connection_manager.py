"""Connection Manager."""
import json
import os

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import OUTPUT_CONFIG_PATH, XRAY_LOCATION_ASSET
from src.services.tun2proxy_service import Tun2ProxyService
from src.services.xray_service import XrayService


class ConnectionManager:
    """Manages VPN/Proxy connections."""
    
    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager
        self._xray_service = XrayService()
        self._tun2proxy_service = Tun2ProxyService()
        self._current_connection = None
        
    def connect(self, file_path: str, mode: str) -> bool:
        """
        Establish connection.
        mode: 'proxy' or 'vpn'
        """
        # Load config
        config, _ = self._config_manager.load_config(file_path)
        if not config:
            return False
            
        # Stop existing processes if any (don't call full disconnect to avoid race)
        if self._current_connection:
            if self._current_connection.get('xray_pid'):
                self._xray_service.stop()
            if self._current_connection.get('tun_pid'):
                self._tun2proxy_service.stop(self._current_connection['tun_pid'])
        
        # Process config for Xray
        processed_config = self._process_config(config)
        
        # Save processed config
        with open(OUTPUT_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(processed_config, f, indent=2)
            
        # Start Xray
        xray_pid = self._xray_service.start(OUTPUT_CONFIG_PATH)
        if not xray_pid:
            return False
            
        # Start Tun2Proxy if VPN mode
        tun_pid = None
        
        if mode == 'vpn':
            socks_port = self._get_socks_port(processed_config)
            bypass_ips = self._get_bypass_ips(processed_config)
            
            tun_pid = self._tun2proxy_service.start(socks_port, bypass_ips)
            
            if not tun_pid:
                self._xray_service.stop()
                return False
                
        self._current_connection = {
            'mode': mode,
            'xray_pid': xray_pid,
            'tun_pid': tun_pid,
            'file': file_path
        }
        return True

    def disconnect(self) -> bool:
        """Disconnect current connection."""
        if not self._current_connection:
            return True
            
        # Stop Tun2Proxy first
        if self._current_connection['tun_pid']:
            self._tun2proxy_service.stop(self._current_connection['tun_pid'])
            
        # Stop Xray
        if self._current_connection['xray_pid']:
            self._xray_service.stop()
            
        self._current_connection = None
        return True

    def _process_config(self, config: dict) -> dict:
        """Process config for Xray usage."""
        # Deep copy to avoid modifying original
        new_config = json.loads(json.dumps(config))
        
        # Ensure log settings
        new_config['log'] = {
            "loglevel": "info",
            "access": "",
            "error": ""
        }
        
        # Ensure asset location
        os.environ['XRAY_LOCATION_ASSET'] = XRAY_LOCATION_ASSET
        
        # Force IP Strategy: Resolve domain and patch config
        self._resolve_and_patch_config(new_config)
        
        return new_config

    def _resolve_and_patch_config(self, config: dict):
        """
        Finds the proxy server address, resolves it to an IP,
        replaces the address with the IP, and sets SNI/Host to the original domain.
        """
        import socket
        
        for outbound in config.get('outbounds', []):
            protocol = outbound.get('protocol')
            if protocol in ['vless', 'vmess', 'trojan', 'shadowsocks']:
                settings = outbound.get('settings', {})
                
                # Locate the server object
                server_obj = None
                if 'vnext' in settings and settings['vnext']:
                    server_obj = settings['vnext'][0]
                elif 'servers' in settings and settings['servers']:
                    server_obj = settings['servers'][0]
                
                if server_obj and 'address' in server_obj:
                    domain = server_obj['address']
                    
                    # Check if it's already an IP
                    try:
                        socket.inet_aton(domain)
                        continue # Already an IP
                    except socket.error:
                        pass # It's a domain
                    
                    try:
                        # Resolve to single IP
                        ip = socket.gethostbyname(domain)
                        logger.info(f"[ConnectionManager] Force IP: Resolved {domain} to {ip}")
                        
                        # 1. Replace address with IP
                        server_obj['address'] = ip
                        
                        # 2. Ensure SNI/Host is set to original domain
                        stream_settings = outbound.get('streamSettings', {})
                        if 'streamSettings' not in outbound:
                            outbound['streamSettings'] = stream_settings
                            
                        # TLS SNI
                        security = stream_settings.get('security', 'none')
                        if security == 'tls':
                            tls_settings = stream_settings.get('tlsSettings', {})
                            if 'tlsSettings' not in stream_settings:
                                stream_settings['tlsSettings'] = tls_settings
                            
                            if 'serverName' not in tls_settings or not tls_settings['serverName']:
                                tls_settings['serverName'] = domain
                                logger.info(f"[ConnectionManager] Set TLS SNI to {domain}")
                        elif security == 'reality':
                             reality_settings = stream_settings.get('realitySettings', {})
                             if 'realitySettings' not in stream_settings:
                                 stream_settings['realitySettings'] = reality_settings
                             if 'serverName' not in reality_settings or not reality_settings['serverName']:
                                 reality_settings['serverName'] = domain
                                 logger.info(f"[ConnectionManager] Set Reality SNI to {domain}")

                        # WS Host
                        network = stream_settings.get('network', '')
                        if network == 'ws':
                            ws_settings = stream_settings.get('wsSettings', {})
                            if 'wsSettings' not in stream_settings:
                                stream_settings['wsSettings'] = ws_settings
                            
                            headers = ws_settings.get('headers', {})
                            if 'headers' not in ws_settings:
                                ws_settings['headers'] = headers
                                
                            if 'Host' not in headers or not headers['Host']:
                                headers['Host'] = domain
                                logger.info(f"[ConnectionManager] Set WS Host to {domain}")
                                
                        # HTTPUpgrade Host
                        if network == 'httpupgrade':
                            httpupgrade_settings = stream_settings.get('httpupgradeSettings', {})
                            if 'httpupgradeSettings' not in stream_settings:
                                stream_settings['httpupgradeSettings'] = httpupgrade_settings
                            
                            if 'host' not in httpupgrade_settings or not httpupgrade_settings['host']:
                                httpupgrade_settings['host'] = domain
                                logger.info(f"[ConnectionManager] Set HTTPUpgrade Host to {domain}")

                    except Exception as e:
                        logger.error(f"[ConnectionManager] Failed to resolve/patch {domain}: {e}")

    def _get_socks_port(self, config: dict) -> int:
        """Extract SOCKS port from config, overriding with user preference."""
        # Get user configured port
        user_port = self._config_manager.get_proxy_port()
        
        # We also need to update the config to listen on this port
        # This is a bit tricky because we need to find the inbound and update it
        for inbound in config.get('inbounds', []):
            if inbound.get('protocol') == 'socks':
                inbound['port'] = user_port
            elif inbound.get('protocol') == 'http':
                # Usually we want http port to be different, or maybe same if sniffing?
                # For now let's just update socks port as that's what tun2proxy uses
                pass
                
        return user_port

    def _get_bypass_ips(self, config: dict) -> list:
        """
        Extract IPs to bypass.
        Since config is already processed, the server address is already an IP.
        """
        bypass_list = []
        
        for outbound in config.get('outbounds', []):
            protocol = outbound.get('protocol')
            if protocol in ['vless', 'vmess', 'trojan', 'shadowsocks']:
                settings = outbound.get('settings', {})
                server_obj = None
                if 'vnext' in settings and settings['vnext']:
                    server_obj = settings['vnext'][0]
                elif 'servers' in settings and settings['servers']:
                    server_obj = settings['servers'][0]
                
                if server_obj and 'address' in server_obj:
                    bypass_list.append(server_obj['address'])
                    break # Only bypass the first/main proxy
        
        return bypass_list
