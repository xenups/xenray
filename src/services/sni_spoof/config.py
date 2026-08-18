"""SNI-spoof service configuration — built from the persisted SettingsRepository.

The listener is a transparent TCP relay (like the reference patterniha script):
Xray's outbound server address is rewritten to 127.0.0.1:LISTEN_PORT, the admin
listener receives the raw TLS bytes and forwards them to CONNECT_IP:CONNECT_PORT
while injecting the fake ClientHello (wrong_seq). So CONNECT_IP/CONNECT_PORT are
the REAL proxy-server target and ARE part of the contract.

``DATA_MODE``/``BYPASS_METHOD`` are fixed at "tls"/"wrong_seq" (the only
implemented reference paths).

The settings getters are read defensively (``getattr`` with the plan defaults):
WS1 owns the repository getters and lands them separately; this module must
import cleanly either way.
"""

# SettingsRepository imported lazily inside build_config(): WS1 owns the SNI
# getter methods; this module must import cleanly even mid-refactor (tests,
# non-Windows dev).

DEFAULTS = {
    "FAKE_SNI": "chatgpt.com",
    "CONNECT_IP": "185.193.30.94",
    "CONNECT_PORT": 443,
    "LISTEN_HOST": "127.0.0.1",
    "LISTEN_PORT": 40443,
}

DATA_MODE = "tls"
BYPASS_METHOD = "wrong_seq"

_GETTERS = {
    "FAKE_SNI": ("get_sni_fake_sni", "get_sni_fake_sni"),
    "CONNECT_IP": ("get_sni_connect_ip", "get_sni_connect_ip"),
    "CONNECT_PORT": ("get_sni_connect_port", "get_sni_connect_port"),
    "LISTEN_HOST": ("get_sni_listen_host", "get_sni_listen_host"),
    "LISTEN_PORT": ("get_sni_listen_port", "get_sni_listen_port"),
}


def _read_field(repo, field: str, default):
    getter_name = _GETTERS[field][0]
    getter = getattr(repo, getter_name, None)
    if getter is None:
        return default
    try:
        return getter()
    except Exception:
        return default


def _disk_connect_fields() -> dict:
    """The user's persisted CONNECT_IP/CONNECT_PORT, read straight from disk.

    These two must reflect ONLY the user's SNI setting (the listener relays to it
    and the WinDivert filter targets it). They are read directly from a fresh
    SettingsRepository so no Xray-config-derived repo/argument can ever override
    them.
    """
    from src.repositories.settings_repository import SettingsRepository

    repo = SettingsRepository()
    try:
        return {
            "CONNECT_IP": repo.get_sni_connect_ip(),
            "CONNECT_PORT": repo.get_sni_connect_port(),
        }
    except Exception:
        return {
            "CONNECT_IP": DEFAULTS["CONNECT_IP"],
            "CONNECT_PORT": DEFAULTS["CONNECT_PORT"],
        }


def build_config(settings_repo=None) -> dict:
    """Assemble the persisted fields (plus fixed mode/method) into a config dict.

    FAKE_SNI/LISTEN_* are read from the given repository (defaults to disk);
    CONNECT_IP/CONNECT_PORT are ALWAYS read directly from disk via
    SettingsRepository.get_sni_connect_ip() — never from an argument that could
    have been populated from the Xray outbound config.
    """
    if settings_repo is None:
        from src.repositories.settings_repository import SettingsRepository

        settings_repo = SettingsRepository()
    config = {}
    for field in ("FAKE_SNI", "LISTEN_HOST", "LISTEN_PORT"):
        config[field] = _read_field(settings_repo, field, DEFAULTS[field])
    config.update(_disk_connect_fields())
    config["DATA_MODE"] = DATA_MODE
    config["BYPASS_METHOD"] = BYPASS_METHOD
    return config
