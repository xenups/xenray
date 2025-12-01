# XenRay

A modern, lightweight Xray client for Windows and Linux/macOS, focusing on simplicity and enhancing VPN experience.

## Features

- ✅ Clean DDD Architecture
- ✅ Cross-platform (Windows, Linux, macOS) with Flet
- ✅ Proxy and VPN modes
- ✅ Real-time log viewing
- ✅ Recent files management
- ✅ Modern, responsive UI

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

The application follows Domain-Driven Design (DDD) principles:

```
src/
├── domain/              # Business logic (UI-agnostic)
│   ├── entities/        # Business objects
│   ├── value_objects/   # Immutable values
│   ├── services/        # Domain services
│   └── repositories/    # Repository interfaces
├── application/         # Use cases & orchestration
│   ├── services/        # Application services
│   └── use_cases/       # Business workflows
├── infrastructure/      # External dependencies
│   ├── repositories/    # Repository implementations
│   ├── services/        # External services (Xray, Tun2proxy)
│   └── utils/          # Utilities
├── presentation/        # Flet UI layer
└── config/             # Configuration
```

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

## License

AGPL-3.0-or-later
