# XenRay

A modern, lightweight Xray GUI client for Windows and Linux, focusing on simplicity and enhancing VPN experience.

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)

## Features

- 🔐 **Dual Mode** - VPN (system-wide tun) and Proxy (SOCKS5) modes
- 🌍 **Server Management** - Import servers via VLESS links or subscription URLs
- 📊 **Latency Testing** - Batch test all servers with visual feedback
- 🎨 **Apple Glass UI** - Modern glassmorphism design with dynamic connection status glow
- 📥 **System Tray** - Background operation with quick taskbar controls
- 👻 **Stealth Mode** - Fully hidden console windows for all core processes
- 🎌 **Country Flags** - Auto-detect server location with GeoIP
- 📝 **Real-time Logs** - Monitor connection status and debug issues
- ⚡ **Auto Updates** - One-click Xray core and app updates (GitHub Releases)
- 🌐 **Internationalization** - Full support for English, Persian (Farsi), Russian, and Chinese

## Gallery

<div align="center">
  <img src="https://raw.githubusercontent.com/xenups/xenray/refs/heads/main/screenshots/main.png" alt="Main Window" width="800"/>
  <p><em>Modern Glass UI with Server List</em></p>
</div>

<div align="center">
  <img src="https://raw.githubusercontent.com/xenups/xenray/refs/heads/main/screenshots/settings.png" alt="Settings" width="800"/>
  <p><em>Comprehensive Settings & Routing</em></p>
</div>

## Installation

### Using Poetry (Recommended)

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Clone and install
git clone https://github.com/xenups/xenray.git
cd xenray
poetry install

# Run
poetry run xenray
```

### Using pip

```bash
pip install flet-desktop requests psutil loguru pystray Pillow
python src/main.py
```

## Usage

```bash
# Standard run
poetry run xenray

# Linux: Install polkit for passwordless VPN mode
poetry run xenray --install-policy
```

### Quick Start
1. Open XenRay
2. Click the server list icon (bottom card)
3. Click **+** to add a server (paste VLESS link) or subscription URL
4. Select a server and click the power button to connect

## Architecture

```
src/
├── core/                    # Core application logic
│   ├── config_manager.py    # Configuration persistence
│   ├── connection_manager.py # Main connection flow logic
│   ├── subscription_manager.py # Subscription handling
│   ├── i18n.py              # Internationalization system
│   ├── flag_colors.py       # Dynamic gradient generation
│   └── constants.py         # Global constants
│
├── services/                # External service integrations
│   ├── xray_service.py      # Xray core process management
│   ├── singbox_service.py   # Sing-box (TUN) integration
│   ├── latency_tester.py    # Real-time latency checking
│   ├── geoip_service.py     # IP location resolution
│   ├── connection_tester.py # Connectivity verification
│   └── app_update_service.py # GitHub release updater
│
├── ui/                      # Flet-based UI layer
│   ├── main_window.py       # Main application window
│   ├── server_list.py       # Virtualized server list view
│   ├── log_viewer.py        # Real-time log console
│   │
│   ├── components/          # Reusable widgets
│   │   ├── connection_button.py # Animated connect button
│   │   ├── server_card.py       # Selected server display
│   │   ├── settings_drawer.py   # Settings slide-out
│   │   ├── logs_drawer.py       # Logs slide-out
│   │   ├── toast.py             # Custom notification system
│   │   ├── timer_display.py     # Connection duration timer
│   │   └── add_server_dialog.py # Config import dialog
│   │
│   └── builders/            # UI composite builders
│       └── ui_builder.py    # Common UI patterns
│
├── utils/                   # Shared utilities
│   ├── network_utils.py     # MTU/Network detection
│   ├── process_utils.py     # Process hiding/management
│   ├── platform_utils.py    # OS-specific helpers
│   ├── link_parser.py       # VLESS/VMess/Trojan parser
│   └── file_utils.py        # File I/O helpers
│
└── main.py                  # Entry point
```

## Development

```bash
# Install dev dependencies
poetry install --with dev

# Format code
poetry run black src/

# Type checking
poetry run mypy src/

# Run tests
poetry run pytest
```

### Building

```bash
# Build standalone executable
python build_pyinstaller.py

# Or directly with PyInstaller
pyinstaller XenRay.spec
```

## Requirements

- Python 3.10+
- Windows 10+ or Linux
- Admin/root for VPN mode (uses tun interface)

## License

[AGPL-3.0-or-later](LICENSE)

---

Made with ❤️ by [Xenups](https://github.com/xenups)
