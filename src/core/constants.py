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
APP_VERSION = os.getenv("APP_VERSION", "0.1.8-alpha")
GITHUB_REPO = os.getenv("GITHUB_REPO", "xenups/xenray")
UPDATE_DOWNLOAD_TIMEOUT = float(os.getenv("UPDATE_DOWNLOAD_TIMEOUT", "60"))
UPDATE_MIN_FILE_SIZE = int(os.getenv("UPDATE_MIN_FILE_SIZE", "1048576"))
XRAY_VERSION = os.getenv("XRAY_VERSION", "25.12.8")
SINGBOX_VERSION = os.getenv("SINGBOX_VERSION", "1.12.13")
ARCH = os.getenv("ARCH", "64")

# Application Limits
MAX_RECENT_FILES = int(os.getenv("MAX_RECENT_FILES", "20"))

# Placeholder PIDs
PLACEHOLDER_XRAY_PID = int(os.getenv("PLACEHOLDER_XRAY_PID", "-999999"))
PLACEHOLDER_SINGBOX_PID = int(os.getenv("PLACEHOLDER_SINGBOX_PID", "-999997"))

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
SINGBOX_PID_FILE = os.path.join(TMPDIR, "singbox.pid")

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
SINGBOX_EXECUTABLE = os.path.join(
    BIN_DIR, f"sing-box{PlatformUtils.get_binary_suffix()}"
)

# Sing-box config and log paths
SINGBOX_CONFIG_PATH = os.path.join(TMPDIR, "singbox_config.json")
SINGBOX_LOG_FILE = os.path.join(TMPDIR, "xenray_singbox.log")

# Xray geo files directory (geoip.dat, geosite.dat are in bin/)
XRAY_LOCATION_ASSET = BIN_DIR

# Temp root for Xray and Singbox
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

# Sing-box Rule Sets (from environment)
SINGBOX_RULE_SETS = {
    "ir": [
        os.getenv(
            "SINGBOX_RULESET_IR_GEOIP",
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs",  # noqa: E501
        ),
        os.getenv(
            "SINGBOX_RULESET_IR_GEOSITE",
            "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs",  # noqa: E501
        ),
    ],
    "cn": [
        os.getenv(
            "SINGBOX_RULESET_ADS_GEOSITE",
            "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-category-ads-all.srs",  # noqa: E501
        ),
        os.getenv(
            "SINGBOX_RULESET_CN_GEOIP",
            "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",  # noqa: E501
        ),
    ],
    "ru": [
        os.getenv(
            "SINGBOX_RULESET_RU",
            "https://github.com/legiz-ru/sb-rule-sets/raw/main/ru-bundle.srs",
        )
    ],
}
