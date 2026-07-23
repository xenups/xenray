import os
import tempfile
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

from src.utils.platform_utils import PlatformUtils

# Load .env from project root
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")

# Application version from environment
APP_VERSION = os.getenv("APP_VERSION", "0.2.1-beta")

# Window dimensions
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 550
GITHUB_REPO = os.getenv("GITHUB_REPO", "xenups/xenray")
UPDATE_DOWNLOAD_TIMEOUT = float(os.getenv("UPDATE_DOWNLOAD_TIMEOUT", "60"))
UPDATE_MIN_FILE_SIZE = int(os.getenv("UPDATE_MIN_FILE_SIZE", "1048576"))
XRAY_VERSION = os.getenv("XRAY_VERSION", "26.7.11")
# WINTUN_DLL — required for Xray native TUN on Windows
WINTUN_DLL = os.path.join(os.path.join(os.path.join(Path(__file__).parent.parent.parent, "bin"), "wintun.dll"))
WINTUN_DOWNLOAD_URL = os.getenv(
    "WINTUN_DOWNLOAD_URL",
    "https://www.wintun.net/builds/wintun-0.14.1.zip",
)
ARCH = os.getenv("ARCH", "64")

# Application Limits
MAX_RECENT_FILES = int(os.getenv("MAX_RECENT_FILES", "20"))

# Placeholder PIDs
PLACEHOLDER_XRAY_PID = int(os.getenv("PLACEHOLDER_XRAY_PID", "-999999"))

# Temporary directory (cross-platform)
if PlatformUtils.get_platform() == "windows":
    # Windows: Use system temp directory
    TMPDIR = os.path.join(tempfile.gettempdir(), "xenray")
elif PlatformUtils.get_platform() == "macos":
    # macOS: Use system temp or user cache directory
    TMPDIR = os.path.join(os.path.expanduser("~/Library/Caches"), "xenray")
else:
    # Linux: Use /tmp or TMPDIR env var
    TMPDIR = os.environ.get("TMPDIR", "/tmp/xenray")

# Log files
EARLY_LOG_FILE = os.path.join(TMPDIR, "xenray_app.log")
XRAY_LOG_FILE = os.path.join(TMPDIR, "xenray_xray.log")
OUTPUT_CONFIG_PATH = os.path.join(TMPDIR, "xenray_config.json")
XRAY_PID_FILE = os.path.join(TMPDIR, "xray.pid")

# Configuration directory
CONFIG_DIR = os.path.expanduser("~/.config/xenray")
LAST_FILE_PATH = os.path.join(CONFIG_DIR, "last_entry.txt")
RECENT_FILES_PATH = os.path.join(CONFIG_DIR, "recent_files.json")

# Socket path for IPC
SOCKET_PATH = os.path.join(TMPDIR, "xenray.sock")

# AppImage directory (Legacy support) / Root directory
APPDIR = PlatformUtils.get_app_dir()  # For bundled assets

# Executable directory for external resources (bin/, scripts/)
EXECDIR = PlatformUtils.get_executable_dir()

# Local directories
ASSETS_DIR = os.path.join(APPDIR, "assets")

# Binary directory - platform specific
# For development: bin/darwin-arm64/, bin/windows-x86_64/, etc.
# For releases: bin/ (flat structure with platform-specific builds)
BIN_DIR_PLATFORM = PlatformUtils.get_platform_bin_dir(os.path.join(EXECDIR, "bin"))
BIN_DIR_FLAT = os.path.join(EXECDIR, "bin")

# Use platform-specific directory if it exists, otherwise use flat structure
if os.path.exists(BIN_DIR_PLATFORM):
    BIN_DIR = BIN_DIR_PLATFORM
else:
    BIN_DIR = BIN_DIR_FLAT

# Executable paths with platform-specific extensions
XRAY_EXECUTABLE = os.path.join(BIN_DIR, f"xray{PlatformUtils.get_binary_suffix()}")

# Sing-box executable paths
SINGBOX_EXECUTABLE = os.path.join(BIN_DIR, f"sing-box{PlatformUtils.get_binary_suffix()}")
SINGBOX_CONFIG_PATH = os.path.join(TMPDIR, "singbox_config.json")
SINGBOX_LOG_FILE = os.path.join(TMPDIR, "xenray_singbox.log")
SINGBOX_PID_FILE = os.path.join(TMPDIR, "singbox.pid")
SINGBOX_RULE_SETS = {
    "ir": [
        "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-ir.srs",
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-ir.srs",
    ],
    "cn": [
        "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs",
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
    ],
    "ru": [
        "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-ru.srs",
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-ru.srs",
    ],
}

# Xray geo files directory (geoip.dat, geosite.dat in assets/rules or bin/)
RULES_DIR = os.path.join(ASSETS_DIR, "rules")
if os.path.exists(os.path.join(RULES_DIR, "geosite.dat")):
    XRAY_LOCATION_ASSET = RULES_DIR
else:
    XRAY_LOCATION_ASSET = BIN_DIR

# Temp root for Xray
TEMP_ROOT = TMPDIR

# Fonts (from environment)
FONT_URLS = {
    "Roboto": os.getenv(
        "FONT_URL_ROBOTO",
        "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
    ),
    "RobotoBold": os.getenv(
        "FONT_URL_ROBOTO_BOLD",
        "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf",
    ),
}

# DNS Providers (from environment)
DNS_PROVIDERS = {
    "local_resolver": {
        "tag": "bootstrap",
        "type": "udp",
        "server": os.getenv("DNS_LOCAL_SERVER", "8.8.8.8"),
        "detour": "direct",
    },
    "proxy_resolver": {
        "tag": "remote_proxy",
        "type": "udp",
        "server": os.getenv("DNS_REMOTE_SERVER", "1.1.1.1"),
        "detour": "proxy",
    },
    "bypass_list": os.getenv(
        "DNS_BYPASS_LIST",
        "8.8.8.8,8.8.4.4,1.1.1.1,1.0.0.1,dns.google,cloudflare-dns.com",
    ).split(","),
}

# Xray country geoip/geosite codes used for per-country direct routing
# These map country setting values → Xray geoip/geosite tag names
XRAY_COUNTRY_GEOIP: dict = {
    "ir": ["geoip:ir"],
    "cn": ["geoip:cn"],
    "ru": ["geoip:ru"],
}

# ---------------------------------------------------------------------------
# Protocol / type string constants — NO hardcoded strings in business logic
# ---------------------------------------------------------------------------

# Inbound / Outbound protocols
PROTOCOL_TUN = "tun"
PROTOCOL_SOCKS = "socks"
PROTOCOL_HTTP = "http"
PROTOCOL_VLESS = "vless"
PROTOCOL_VMESS = "vmess"
PROTOCOL_TROJAN = "trojan"
PROTOCOL_SHADOWSOCKS = "shadowsocks"
PROTOCOL_HYSTERIA2 = "hysteria2"
PROTOCOL_FREEDOM = "freedom"
PROTOCOL_BLACKHOLE = "blackhole"
PROTOCOL_DNS = "dns"
PROTOCOL_LOOPBACK = "loopback"

# Connection modes
MODE_VPN = "vpn"
MODE_PROXY = "proxy"

# Outbound / inbound tags
TAG_DIRECT = "direct"
TAG_PROXY = "proxy"
TAG_BLOCK = "block"

# Transport network types
NETWORK_TCP = "tcp"
NETWORK_WS = "ws"
NETWORK_GRPC = "grpc"
NETWORK_QUIC = "quic"
NETWORK_HTTP3 = "http3"
NETWORK_XHTTP = "xhttp"
NETWORK_HTTPUPGRADE = "httpupgrade"
NETWORK_SPLITHTTP = "splithttp"
NETWORK_H3 = "h3"
NETWORK_H2 = "h2"

# Security types
SECURITY_TLS = "tls"
SECURITY_REALITY = "reality"
SECURITY_NONE = "none"
TLS_SETTINGS = "tlsSettings"
REALITY_SETTINGS = "realitySettings"

# DNS protocol types
DNS_UDP = "udp"
DNS_TCP = "tcp"
DNS_DOH = "doh"
DNS_DOT = "dot"
DNS_DOQ = "doq"

# DNS query strategies
DNS_USE_IP = "UseIP"
DNS_USE_IPV4 = "UseIPv4"
DNS_USE_IPV6 = "UseIPv6"

# Domain strategy values
DOMAIN_ASIS = "AsIs"
DOMAIN_IP_IF_NON_MATCH = "IPIfNonMatch"
DOMAIN_IP_ON_DEMAND = "IPOnDemand"

# Geo prefix tags
GEOIP_PREFIX = "geoip:"
GEOSITE_PREFIX = "geosite:"

# Sniffing dest-override values
SNIFF_DEST_OVERRIDE = ["http", "tls", "quic"]

# Routing rule type
RULE_FIELD = "field"

# Stream setting keys
STREAM_WS_SETTINGS = "wsSettings"
STREAM_HTTPUPGRADE_SETTINGS = "httpupgradeSettings"
STREAM_XHTTP_SETTINGS = "xhttpSettings"
STREAM_HEADERS = "headers"
STREAM_HOST = "host"
HEADER_HOST = "Host"  # HTTP header name (capital H)
STREAM_MODE = "mode"
STREAM_SERVER_NAME = "serverName"
STREAM_PATH = "path"

# Config dict keys
CONFIG_DNS = "dns"
CONFIG_ROUTING = "routing"
CONFIG_RULES = "rules"
CONFIG_INBOUNDS = "inbounds"
CONFIG_OUTBOUNDS = "outbounds"
CONFIG_SETTINGS = "settings"
CONFIG_STREAM_SETTINGS = "streamSettings"
CONFIG_DOMAIN_STRATEGY = "domainStrategy"
CONFIG_QUERY_STRATEGY = "queryStrategy"
CONFIG_PROTOCOL = "protocol"
CONFIG_ADDRESS = "address"
CONFIG_PORT = "port"
CONFIG_TAG = "tag"
CONFIG_IP = "ip"
CONFIG_DOMAIN = "domain"
CONFIG_DOMAINS = "domains"  # plural — used in DNS data storage
CONFIG_SERVERS = "servers"
CONFIG_OUTBOUND_TAG = "outboundTag"
CONFIG_NETWORK = "network"
CONFIG_SNIFFING = "sniffing"
CONFIG_ENABLED = "enabled"
CONFIG_DEST_OVERRIDE = "destOverride"
CONFIG_METADATA_ONLY = "metadataOnly"
CONFIG_ROUTE_ONLY = "routeOnly"
