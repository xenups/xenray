import unittest
from unittest.mock import Mock

from src.core.app_context import AppContext
from src.services.xray_config_processor import XrayConfigProcessor
from src.utils.link_parser import LinkParser


class TestLinkParserStrict(unittest.TestCase):
    def test_host_derivation_sni_exists(self):
        """
        Verify that when host is missing in the link:
        Address = 'cdn.com', SNI = 'real.com' -> Host derived as 'real.com'
        """
        link = "vless://uuid@cdn.com:443?type=splithttp&security=tls&sni=real.com#test"
        result = LinkParser.parse_link(link)
        config = result["config"]
        outbound = config["outbounds"][0]
        stream = outbound["streamSettings"]

        # Check derived host in xhttpSettings
        self.assertEqual(stream["xhttpSettings"]["host"], "real.com")
        # Check derived host in tlsSettings
        self.assertEqual(stream["tlsSettings"]["serverName"], "real.com")
        # Check raw address remains untouched
        self.assertEqual(outbound["settings"]["vnext"][0]["address"], "cdn.com")

    def test_host_derivation_no_sni(self):
        """
        Verify that when host is missing and SNI is missing (or same as address):
        Address = 'real.com' -> Host derived as 'real.com'
        """
        link = "vless://uuid@real.com:443?type=splithttp&security=tls#test"
        result = LinkParser.parse_link(link)
        config = result["config"]
        outbound = config["outbounds"][0]
        stream = outbound["streamSettings"]

        # Check derived host
        self.assertEqual(stream["xhttpSettings"]["host"], "real.com")
        # Check raw address
        self.assertEqual(outbound["settings"]["vnext"][0]["address"], "real.com")

    def test_host_derivation_explicit_host(self):
        """
        Verify that when host is explicit, it takes precedence over SNI/Address.
        Address = 'cdn.com', SNI = 'sni.com', Host = 'custom.com' -> Host = 'custom.com'
        """
        link = "vless://uuid@cdn.com:443?type=splithttp&security=tls&sni=sni.com&host=custom.com#test"
        result = LinkParser.parse_link(link)
        config = result["config"]
        outbound = config["outbounds"][0]
        stream = outbound["streamSettings"]

        # Check explicit host
        self.assertEqual(stream["xhttpSettings"]["host"], "custom.com")
        # Check SNI
        self.assertEqual(stream["tlsSettings"]["serverName"], "sni.com")

    def test_extended_splithttp_params(self):
        """
        Verify correct parsing of extended SplitHTTP params without default injection.
        """
        link = (
            "vless://uuid@host:443?type=splithttp"
            "&mode=stream-up"
            "&noSSEHeader=true"
            "&xPaddingBytes=100"
            "&scStreamUpServerSecs=30"
            "&scMaxBufferedPosts=50"
            "#test"
        )

        result = LinkParser.parse_link(link)
        settings = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]

        self.assertEqual(settings.get("mode"), "stream-up")
        self.assertEqual(settings.get("noSSEHeader"), True)
        self.assertEqual(settings.get("xPaddingBytes"), "100")
        self.assertEqual(settings.get("scStreamUpServerSecs"), "30")
        self.assertEqual(settings.get("scMaxBufferedPosts"), 50)

    def test_extended_splithttp_params_missing(self):
        """
        Verify defaults are NOT injected when params are missing.
        """
        link = "vless://uuid@host:443?type=splithttp#test"
        result = LinkParser.parse_link(link)
        settings = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]

        self.assertNotIn("mode", settings)
        self.assertNotIn("noSSEHeader", settings)
        self.assertNotIn("xPaddingBytes", settings)


class TestXrayConfigProcessorStrict(unittest.TestCase):
    def setUp(self):
        self.mock_config_manager = Mock(spec=AppContext)
        self.mock_config_manager.load_dns_config.return_value = []
        self.mock_config_manager.get_proxy_port.return_value = 10805  # Mock user port
        self.processor = XrayConfigProcessor(self.mock_config_manager)

    def test_processor_resolves_address_for_bootstrap(self):
        """
        Verify processor resolves domain to IP for bootstrap DNS.
        This allows all DNS queries to go through the tunnel.
        """
        config = {
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "google.com", "port": 443}]},
                    "streamSettings": {"network": "tcp"},
                }
            ]
        }

        processed = self.processor.process_config(config)

        # Assert address is resolved to IP
        resolved_address = processed["outbounds"][0]["settings"]["vnext"][0]["address"]

        # Should be an IP now, not the domain
        import ipaddress

        try:
            ipaddress.ip_address(resolved_address)
            is_ip = True
        except ValueError:
            is_ip = False

        self.assertTrue(is_ip, f"Expected IP address, got: {resolved_address}")
        self.assertNotEqual(resolved_address, "google.com", "Address should be resolved to IP")


if __name__ == "__main__":
    unittest.main()
