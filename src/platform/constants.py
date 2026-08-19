"""Platform-layer constants — every OS string in one place.

No raw ``powershell``/``netsh``/``ipconfig`` or adapter/registry names should
appear in business logic. Import from here (or from ``windows.constants`` when
platform-specific) so the rest of the codebase is platform-agnostic.
"""

from __future__ import annotations

# --- Universal OS command names (no raw strings in business logic) ---
CMD_POWERSHELL = "powershell"
CMD_NETSH = "netsh"
CMD_IPCONFIG = "ipconfig"
CMD_ROUTE = "route"
CMD_SCUTIL = "scutil"
CMD_IP = "ip"

# --- XenRay TUN adapter (single source of truth) ---
TUN_ADAPTER_NAME = "xenray-tun"

# --- NRPT comment marker used to tag/remove only XenRay rules ---
NRPT_COMMENT_TAG = "XenRay"

# --- Xray install/update pipeline ---
XRAY_GITHUB_RELEASES_API_URL = "https://api.github.com/repos/XTLS/Xray-core/releases"
XRAY_CORE_DOWNLOAD_BASE_URL = "https://github.com/XTLS/Xray-core/releases/download"
XRAY_CORE_ASSET_EXTENSION = ".zip"
XRAY_CORE_ZIP_FILENAME = "xray_update.zip"
WINTUN_ZIP_FILENAME = "wintun.zip"
XRAY_DOWNLOAD_CONNECT_TIMEOUT = 15.0  # seconds to establish connection
XRAY_DOWNLOAD_READ_TIMEOUT = 60.0  # seconds between data chunks (prevents infinite stall)
XRAY_DOWNLOAD_CHUNK_SIZE = 65536  # 64 KB read chunks for streaming download
XRAY_DOWNLOAD_MIN_FILE_SIZE = 1024  # bytes — minimum expected file size
XRAY_DOWNLOAD_MAX_RETRIES = 3  # number of download attempts before giving up
XRAY_EXTRACT_RETRIES = 3
XRAY_EXTRACT_RETRY_DELAY_SECONDS = 0.5
XRAY_KILL_GRACE_SECONDS = 0.2  # wait for the OS to release locked file handles

# --- Windows TUN DNS policy ---
# DNS primary/secondary fallbacks when the config supplies none (RFC-compliant
# public resolvers, Cloudflare + Google).
DNS_FALLBACK_V4 = [
    "1.1.1.1",
    "8.8.8.8",
]
