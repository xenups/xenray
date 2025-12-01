# Xenray

A modern, lightweight Xray client for Windows and Linux/macOS, focusing on simplicity and enhancing VPN experience.

## Features

- 🚀 **Lightweight & Fast**: Minimal resource usage with efficient Xray core integration
- 🔒 **Multiple Protocols**: Support for VLESS, VMess, Trojan, and Shadowsocks
- 🌐 **Cross-Platform**: Works on Windows, Linux, and macOS
- 🎯 **Simple CLI**: Easy-to-use command-line interface
- 📦 **Configuration Management**: Import/export configs, manage multiple servers
- 🔄 **Auto-Reconnect**: Automatic reconnection on connection loss
- 📊 **Status Monitoring**: Real-time connection status and resource usage

## Installation

### Prerequisites

- Python 3.8 or higher
- Xray-core binary installed on your system

### Install from source

```bash
git clone https://github.com/xenups/xenray.git
cd xenray
pip install -e .
```

### Install Xray-core

#### Windows
Download the latest Xray-core from [Xray releases](https://github.com/XTLS/Xray-core/releases) and add it to your PATH.

#### Linux
```bash
# Using curl
bash -c "$(curl -L https://github.com/XTLS/Xray-core/releases/latest/download/install-release.sh)" @ install

# Or download manually and add to PATH
```

#### macOS
```bash
# Using Homebrew
brew install xray

# Or download manually
```

## Quick Start

### 1. Add a server

```bash
# Add a VLESS server
xenray server add \
  --id my-server \
  --name "My VPN Server" \
  --address example.com \
  --port 443 \
  --protocol vless \
  --uuid your-uuid-here \
  --network tcp \
  --tls tls

# Add a VMess server
xenray server add \
  --id vmess-server \
  --name "VMess Server" \
  --address example.com \
  --port 443 \
  --protocol vmess \
  --uuid your-uuid-here \
  --network ws \
  --tls tls

# Add a Trojan server
xenray server add \
  --id trojan-server \
  --name "Trojan Server" \
  --address example.com \
  --port 443 \
  --protocol trojan \
  --password your-password-here \
  --network tcp \
  --tls tls
```

### 2. List servers

```bash
xenray server list
```

### 3. Set active server

```bash
xenray server set my-server
```

### 4. Start connection

```bash
xenray start
```

### 5. Check status

```bash
xenray status
```

### 6. Stop connection

```bash
xenray stop
```

## CLI Commands

### Server Management

```bash
# List all servers
xenray server list

# Add a new server
xenray server add --id <id> --name <name> --address <address> --port <port> ...

# Remove a server
xenray server remove <server-id>

# Set active server
xenray server set <server-id>
```

### Connection Control

```bash
# Start connection
xenray start

# Stop connection
xenray stop

# Restart connection
xenray restart

# Show connection status
xenray status
```

### Configuration

```bash
# Show current configuration
xenray config show

# Import configuration from file
xenray config import config.json [--format json|yaml]

# Export configuration to file
xenray config export output.json [--format json|yaml]

# Use custom config file
xenray --config /path/to/config.json start
```

## Configuration

Xenray stores configuration in a JSON file at:
- **Windows**: `%APPDATA%\xenray\config.json`
- **Linux**: `~/.config/xenray/config.json`
- **macOS**: `~/Library/Application Support/xenray/config.json`

### Configuration Structure

```json
{
  "xray_binary": "xray",
  "log_level": "info",
  "auto_reconnect": true,
  "connection_timeout": 10,
  "servers": [
    {
      "id": "server-1",
      "name": "My Server",
      "protocol": "vless",
      "address": "example.com",
      "port": 443,
      "uuid": "your-uuid",
      "network": "tcp",
      "tls": "tls",
      "sni": "example.com"
    }
  ],
  "active_server": "server-1",
  "inbound": {
    "listen": "127.0.0.1",
    "port": 10808,
    "protocol": "socks"
  }
}
```

## Supported Protocols

### VLESS
```bash
xenray server add --protocol vless --uuid <uuid> --network tcp --tls tls
```

### VMess
```bash
xenray server add --protocol vmess --uuid <uuid> --network ws --tls tls
```

### Trojan
```bash
xenray server add --protocol trojan --password <password> --network tcp --tls tls
```

### Shadowsocks
```bash
xenray server add --protocol shadowsocks --password <password>
```

## Network Types

- **tcp**: Standard TCP connection
- **ws**: WebSocket transport
- **grpc**: gRPC transport
- **h2**: HTTP/2 transport

## Development

### Setup development environment

```bash
git clone https://github.com/xenups/xenray.git
cd xenray
pip install -e ".[dev]"
```

### Run tests

```bash
pytest
```

### Run linter

```bash
ruff check xenray/
black --check xenray/
```

## Troubleshooting

### Xray binary not found
Make sure Xray-core is installed and available in your PATH, or specify the path in configuration:
```bash
# Set custom Xray binary path
xenray config show  # Note your config file location
# Edit the config file and set "xray_binary": "/path/to/xray"
```

### Connection fails to start
Check the logs for errors. Increase log level for more details:
```json
{
  "log_level": "debug"
}
```

### Permission denied
On Linux/macOS, ensure you have permissions to bind to the local port (default 10808).

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [Xray-core](https://github.com/XTLS/Xray-core) - The powerful proxy tool
- [V2Ray](https://www.v2ray.com/) - Original inspiration
