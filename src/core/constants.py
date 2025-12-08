import os
import sys
import tempfile

# Temporary directory (cross-platform)
if os.name == 'nt':
    # Windows: Use system temp directory
    TMPDIR = os.path.join(tempfile.gettempdir(), "xenray")
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
if getattr(sys, 'frozen', False):
    # If compiled, use the directory of the executable
    APPDIR = os.path.dirname(sys.executable)
else:
    # If running as script, go up 3 levels from src/core/constants.py
    APPDIR = os.environ.get("APPDIR", os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Local directories
# Local directories
BIN_DIR = os.path.join(APPDIR, "bin")
ASSETS_DIR = os.path.join(APPDIR, "assets")

# Xray executable path
if os.name == 'nt':
    XRAY_EXECUTABLE = os.path.join(BIN_DIR, "xray.exe")
else:
    XRAY_EXECUTABLE = os.path.join(BIN_DIR, "xray")

# Tun2Proxy executable path (Legacy - being replaced by Sing-box)
if os.name == 'nt':
    TUN2PROXY_EXECUTABLE = os.path.join(BIN_DIR, "tun2proxy-bin.exe")
else:
    TUN2PROXY_EXECUTABLE = os.path.join(BIN_DIR, "tun2proxy")

# Sing-box executable path
if os.name == 'nt':
    SINGBOX_EXECUTABLE = os.path.join(BIN_DIR, "sing-box.exe")
else:
    SINGBOX_EXECUTABLE = os.path.join(BIN_DIR, "sing-box")

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
        "https://github.com/SagerNet/sing-geosite/releases/download/20251206075552/geosite-cn.srs"
        # Note: Ideally this should optionally dynamic or we pin a version like you did.
        # Keeping user's URL for now, but moving to constants makes updates easier.
    ],
    "ru": [
        "https://github.com/legiz-ru/sb-rule-sets/raw/main/ru-bundle.srs"
    ],
}

