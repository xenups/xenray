# XenRay

A modern, lightweight Xray GUI client for Windows and Linux, focusing on simplicity and enhancing VPN experience.

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)

## Features

- 🔐 **Dual Mode** - VPN (system-wide tun) and Proxy (SOCKS5) modes
- 🌍 **Server Management** - Import servers via VLESS links or subscription URLs
- 📊 **Latency Testing** - Batch test all servers with visual feedback
- 🎌 **Country Flags** - Auto-detect server location with GeoIP
- 🎨 **Modern UI** - Dark/light themes with smooth animations
- 📝 **Real-time Logs** - Monitor connection status and debug issues
- ⚡ **Auto Updates** - One-click Xray core updates

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
├── core/                    # Configuration & connection management
│   ├── config_manager.py    # Profile/settings persistence
│   ├── connection_manager.py
│   └── subscription_manager.py
│
├── services/                # External integrations
│   ├── xray_service.py      # Xray process management
│   ├── singbox_service.py   # Sing-box (tun) integration
│   ├── latency_tester.py    # Batch latency testing
│   ├── geoip_service.py     # Country detection
│   └── connection_tester.py
│
├── ui/
│   ├── components/          # Reusable UI components
│   │   ├── server_list_header.py
│   │   ├── server_list_item.py
│   │   ├── subscription_list_item.py
│   │   ├── add_server_dialog.py
│   │   ├── connection_button.py
│   │   ├── status_display.py
│   │   ├── server_card.py
│   │   ├── settings_drawer.py
│   │   └── settings_sections.py
│   ├── server_list.py       # Server list orchestration
│   └── main_window.py       # Main window
│
├── utils/                   # Helpers
│   ├── link_parser.py       # VLESS/VMess link parsing
│   ├── process_utils.py
│   └── network_interface.py
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
