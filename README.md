# XenRay

A modern, lightweight Xray client for Windows and Linux/macOS, focusing on simplicity and enhancing VPN experience.

## Features

### Core Functionality
- ✅ Clean DDD Architecture
- ✅ Cross-platform (Windows, Linux, macOS) with Flet
- ✅ Proxy and VPN modes
- ✅ Real-time log viewing
- ✅ Recent files management
- ✅ Server profile management
- ✅ Connection status monitoring

### UI/UX Features
- ✅ **Animated Splash Screen** - Beautiful purple pulsing circle animation with:
  - Rotating outer ring with dynamic opacity
  - Three-layer concentric circles with phase-offset breathing animation
  - Dynamic radial gradients and shadow blur effects (50-80px)
  - Icon pulsing animation (size and opacity)
  - Text fade animations
  - Smooth 25 FPS animations using sine wave calculations
- ✅ Modern, responsive UI with dark/light theme support
- ✅ Pulsing connection button with amber glow during connection
- ✅ Real-time status display with ping measurement
- ✅ Server card with country flags
- ✅ Drawer-based navigation for logs and settings

## Installation

### Using Poetry (Recommended)

```bash
# Install Poetry if you haven't
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Run the application
poetry run gorzray
```

### Using pip

```bash
# Install dependencies
pip install flet requests psutil

# Run the application
python src/main.py
```

## Usage

### Basic Usage

```bash
# Run with Poetry
poetry run gorzray

# Or directly
python src/main.py
```

### Install Polkit Files (Linux only, for passwordless VPN)

```bash
poetry run gorzray --install-policy
```

## Architecture

The application follows a clean, modular architecture:

```
src/
├── core/                # Core business logic
│   ├── config_manager.py    # Profile and configuration management
│   ├── connection_manager.py # Connection state and lifecycle
│   ├── constants.py         # Application constants
│   ├── logger.py            # Logging utilities
│   ├── settings.py          # Settings management
│   └── types.py             # Type definitions
├── services/            # External service integrations
│   ├── dependency_manager.py # Dependency installation
│   ├── geo_installer.py     # GeoIP/GeoSite data management
│   ├── singbox_service.py   # Sing-box integration
│   ├── xray_installer.py    # Xray installation
│   └── xray_service.py      # Xray process management
├── ui/                  # Flet UI layer
│   ├── components/      # Reusable UI components
│   │   ├── app_container.py      # Main app container
│   │   ├── connection_button.py  # Animated connection button
│   │   ├── header.py             # App header with theme toggle
│   │   ├── logs_drawer.py        # Logs navigation drawer
│   │   ├── server_card.py        # Server profile card
│   │   ├── settings_drawer.py    # Settings navigation drawer
│   │   ├── splash_overlay.py     # Animated splash screen ⭐
│   │   └── status_display.py     # Connection status display
│   ├── log_viewer.py    # Log viewing component
│   ├── main_window.py   # Main window orchestration
│   └── server_list.py   # Server list component
├── utils/               # Utility functions
│   ├── country_flags.py # Country flag emoji mapping
│   ├── file_utils.py    # File operations
│   ├── link_parser.py   # V2Ray link parsing
│   ├── network_interface.py # Network interface management
│   └── process_utils.py # Process management
└── main.py              # Application entry point
```

### Splash Screen Implementation

The splash screen (`src/ui/components/splash_overlay.py`) features a sophisticated multi-threaded animation system:

- **Rotating Ring**: Continuous 360° rotation with pulsing border opacity
- **Breathing Circles**: Three concentric circles (outer: 200-240px, middle: 150-180px, inner: 110-130px) with phase-offset sine wave animations
- **Dynamic Effects**: Real-time gradient opacity and shadow blur adjustments (50-80px blur radius)
- **Icon Animation**: Size pulsing (55-60px) with opacity fade
- **Text Effects**: Subtle fade animations for title and subtitle
- **Performance**: Optimized 25 FPS animations using separate threads for each animation layer
- **Color Scheme**: Purple palette (#8b5cf6, #6d28d9, #4c1d95, #a78bfa, #c4b5fd)

## Technical Details

### Animation System
- **Multi-threaded**: Each animation layer runs in its own daemon thread
- **Sine Wave Based**: Natural breathing effect using `sin()` calculations
- **Phase Offset**: Different animation phases create layered visual depth
- **Real-time Updates**: Direct page updates for smooth 25 FPS rendering
- **Resource Management**: Automatic cleanup when splash fades out

### UI Components
- **Connection Button**: State-aware with pulsing amber glow during connection
- **Status Display**: Real-time connection status with ping measurement
- **Server Card**: Displays selected server with country flag and details
- **Theme Support**: Full dark/light mode with smooth transitions

## Development

```bash
# Install dev dependencies
poetry install --with dev

# Run tests
poetry run pytest

# Format code
poetry run black src/

# Type checking
poetry run mypy src/
```

### Building

```bash
# Build with PyInstaller
python build_pyinstaller.py

# Or use the spec file directly
pyinstaller XenRay.spec
```

## License

AGPL-3.0-or-later
