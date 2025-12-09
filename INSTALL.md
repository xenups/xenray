# Installation and Setup Guide for XenRay

## Prerequisites

- Python 3.8 or higher
- Poetry (recommended) or pip

## Installation

### Option 1: Using Poetry (Recommended)

1. **Install Poetry** (if not already installed):
   ```powershell
   # Windows (PowerShell)
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
   
   # Linux/macOS
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Navigate to project directory**:
   ```bash
   cd <project_directory>
   ```

3. **Install dependencies**:
   ```bash
   poetry install
   ```

4. **Run the application**:
   ```bash
   poetry run xenray
   ```

### Option 2: Using pip

1. **Install dependencies**:
   ```bash
   pip install flet requests psutil
   ```

2. **Run the application**:
   ```bash
   python -m src.main
   ```

## First Run

1. Launch the application
2. Click "Browse..." to select your Xray configuration file
3. Toggle "VPN Mode" if needed (default is VPN Mode)
4. Click "Connect"

## Linux-specific: VPN Mode Setup

For passwordless VPN mode on Linux, install Polkit files:

```bash
poetry run xenray --install-policy
# or
python -m src.main --install-policy
```

## Troubleshooting

### Windows: Missing dependencies
```powershell
poetry install --no-root
```

### Linux: Permission issues
```bash
sudo poetry run xenray --install-policy
```

### All platforms: Clear cache
```bash
# Remove temporary files
rm -rf /tmp/xenray  # Linux/macOS
Remove-Item -Recurse -Force $env:TEMP\xenray  # Windows PowerShell
```
