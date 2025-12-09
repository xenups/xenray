import os
import sys
import tempfile
from pathlib import Path

from src.utils.platform_utils import PlatformUtils

# Load environment variables from .env file
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")

# Application version from environment
APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
XRAY_VERSION = os.getenv("XRAY_VERSION", "1.8.24")
SINGBOX_VERSION = os.getenv("SINGBOX_VERSION", "1.10.6")
ARCH = os.getenv("ARCH", "64")

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
TUN_LOG_FILE = os.path.join(TMPDIR, "xenray_tun2proxy.log")
OUTPUT_CONFIG_PATH = os.path.join(TMPDIR, "xenray_config.json")
XRAY_PID_FILE = os.path.join(TMPDIR, "xray.pid")
SINGBOX_PID_FILE = os.path.join(TMPDIR, "singbox.pid")

# Configuration directory
CONFIG_DIR = os.path.expanduser("~/.config/xenray")
LAST_FILE_PATH = os.path.join(CONFIG_DIR, "last_entry.txt")
RECENT_FILES_PATH = os.path.join(CONFIG_DIR, "recent_files.json")

# Socket path for IPC
SOCKET_PATH = os.path.join(TMPDIR, "xenray.sock")

# Maximum number of recent files to store
MAX_RECENT_FILES = 20

# AppImage directory (Legacy support) / Root directory
APPDIR = PlatformUtils.get_app_dir()

# Local directories
ASSETS_DIR = os.path.join(APPDIR, "assets")

# Binary directory - platform specific
# For development: bin/darwin-arm64/, bin/windows-x86_64/, etc.
# For releases: bin/ (flat structure with platform-specific builds)
BIN_DIR_PLATFORM = PlatformUtils.get_platform_bin_dir(os.path.join(APPDIR, "bin"))
BIN_DIR_FLAT = os.path.join(APPDIR, "bin")

# Use platform-specific directory if it exists, otherwise use flat structure
if os.path.exists(BIN_DIR_PLATFORM):
    BIN_DIR = BIN_DIR_PLATFORM
else:
    BIN_DIR = BIN_DIR_FLAT

# Executable paths with platform-specific extensions
XRAY_EXECUTABLE = os.path.join(BIN_DIR, f"xray{PlatformUtils.get_binary_suffix()}")
TUN2PROXY_EXECUTABLE = os.path.join(BIN_DIR, f"tun2proxy-bin{PlatformUtils.get_binary_suffix()}")
SINGBOX_EXECUTABLE = os.path.join(BIN_DIR, f"sing-box{PlatformUtils.get_binary_suffix()}")

# Sing-box config and log paths
SINGBOX_CONFIG_PATH = os.path.join(TMPDIR, "singbox_config.json")
SINGBOX_LOG_FILE = os.path.join(TMPDIR, "xenray_singbox.log")

# Xray geo files directory
XRAY_LOCATION_ASSET = ASSETS_DIR

# Temp root for tun2proxy and run_vpn.sh
TEMP_ROOT = TMPDIR

# Placeholder PIDs
PLACEHOLDER_XRAY_PID = -999999
PLACEHOLDER_TUN2PROXY_PID = -999998
PLACEHOLDER_SINGBOX_PID = -999997

# Fonts
FONT_URLS = {
    "Roboto": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
    "RobotoBold": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf",
}

# DNS Providers
DNS_PROVIDERS = {
    "local_resolver": {
        "tag": "bootstrap",
        "type": "udp",
        "server": "8.8.8.8",
        "detour": "direct",
    },
    "proxy_resolver": {
        "tag": "remote_proxy",
        "type": "udp",
        "server": "1.1.1.1",
        "detour": "proxy",
    },
    "bypass_list": [
        "8.8.8.8",
        "8.8.4.4",
        "1.1.1.1",
        "1.0.0.1",
        "dns.google",
        "cloudflare-dns.com",
    ]
}

# Sing-box Rule Sets
SINGBOX_RULE_SETS = {
    "ir": [
        "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs",
        "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs",
    ],
    "cn": [
        "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs",
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs"
    ],
    "ru": [
        "https://github.com/legiz-ru/sb-rule-sets/raw/main/ru-bundle.srs"
    ],
}

