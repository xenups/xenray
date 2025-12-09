#!/bin/bash
# Build AppImage for Linux distribution
# Usage: ./scripts/build_appimage.sh

set -e  # Exit on error

# Configuration
APP_NAME="XenRay"
VERSION="${1:-2.0.0}"
ARCH=$(uname -m)  # x86_64 or aarch64
BUILD_DIR="build/appimage"
APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================"
echo "Building AppImage for $APP_NAME"
echo "Version: $VERSION"
echo "Architecture: $ARCH"
echo "======================================"

# Check if we're on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}Error: This script must be run on Linux${NC}"
    exit 1
fi

# Check if Python app is built
if [ ! -f "dist/XenRay" ]; then
    echo -e "${YELLOW}Building Python executable first...${NC}"
    python build_pyinstaller.py
fi

# Clean previous build
echo -e "\n${GREEN}Cleaning previous build...${NC}"
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR"

# Create AppDir structure
echo -e "${GREEN}Creating AppDir structure...${NC}"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/metainfo"

# Copy executable
echo -e "${GREEN}Copying executable...${NC}"
cp dist/XenRay "$APPDIR/usr/bin/"
chmod +x "$APPDIR/usr/bin/XenRay"

# Copy assets and binaries
echo -e "${GREEN}Copying assets and binaries...${NC}"
if [ -d "dist/assets" ]; then
    cp -r dist/assets "$APPDIR/usr/bin/"
fi

if [ -d "dist/bin" ]; then
    cp -r dist/bin "$APPDIR/usr/bin/"
    # Make binaries executable
    find "$APPDIR/usr/bin/bin" -type f -exec chmod +x {} \;
fi

# Create desktop entry
echo -e "${GREEN}Creating desktop entry...${NC}"
cat > "$APPDIR/usr/share/applications/${APP_NAME}.desktop" << EOF
[Desktop Entry]
Name=XenRay
Comment=Xray VPN Client for Linux
Exec=XenRay
Icon=xenray
Type=Application
Categories=Network;Security;
Terminal=false
StartupNotify=true
Keywords=VPN;Proxy;Xray;Security;
EOF

# Copy icon (convert from ico if needed)
if [ -f "assets/icon.png" ]; then
    cp "assets/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/xenray.png"
    cp "assets/icon.png" "$APPDIR/xenray.png"
elif [ -f "assets/icon.ico" ]; then
    # Convert ico to png using ImageMagick if available
    if command -v convert &> /dev/null; then
        convert "assets/icon.ico[0]" -resize 256x256 "$APPDIR/usr/share/icons/hicolor/256x256/apps/xenray.png"
        cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/xenray.png" "$APPDIR/xenray.png"
    else
        echo -e "${YELLOW}Warning: ImageMagick not found. Cannot convert icon.${NC}"
        echo -e "${YELLOW}Please provide assets/icon.png manually${NC}"
    fi
fi

# Create AppRun script
echo -e "${GREEN}Creating AppRun script...${NC}"
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
# AppRun script for XenRay

SELF=$(readlink -f "$0")
HERE=${SELF%/*}

# Export library paths
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
export PATH="${HERE}/usr/bin:${PATH}"

# Change to the app directory
cd "${HERE}/usr/bin"

# Run the application
exec "${HERE}/usr/bin/XenRay" "$@"
EOF

chmod +x "$APPDIR/AppRun"

# Create AppStream metadata
echo -e "${GREEN}Creating AppStream metadata...${NC}"
cat > "$APPDIR/usr/share/metainfo/${APP_NAME}.appdata.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop">
  <id>com.xenray.vpn</id>
  <name>XenRay</name>
  <summary>Xray VPN Client</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>AGPL-3.0-or-later</project_license>
  <description>
    <p>
      XenRay is a simple and powerful Xray VPN client for Linux.
      It supports both proxy mode and VPN mode with TUN interface.
    </p>
  </description>
  <url type="homepage">https://github.com/xenups/xenray</url>
  <url type="bugtracker">https://github.com/xenups/xenray/issues</url>
  <releases>
    <release version="${VERSION}" date="$(date +%Y-%m-%d)" />
  </releases>
  <categories>
    <category>Network</category>
    <category>Security</category>
  </categories>
</component>
EOF

# Download appimagetool if not present
APPIMAGETOOL="appimagetool-${ARCH}.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo -e "${GREEN}Downloading appimagetool...${NC}"
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/${APPIMAGETOOL}"
    chmod +x "$APPIMAGETOOL"
fi

# Build AppImage
echo -e "\n${GREEN}Building AppImage...${NC}"
APPIMAGE_NAME="${APP_NAME}-${VERSION}-${ARCH}.AppImage"

# Use appimagetool to create AppImage
./"$APPIMAGETOOL" "$APPDIR" "$APPIMAGE_NAME"

# Make it executable
chmod +x "$APPIMAGE_NAME"

# Calculate checksum
echo -e "${GREEN}Calculating SHA256 checksum...${NC}"
sha256sum "$APPIMAGE_NAME" > "${APPIMAGE_NAME}.sha256"

echo ""
echo "======================================"
echo -e "${GREEN}AppImage Build Successful!${NC}"
echo "======================================"
echo "Output: $APPIMAGE_NAME"
echo "Size: $(du -h "$APPIMAGE_NAME" | awk '{print $1}')"
echo "SHA256: $(cat ${APPIMAGE_NAME}.sha256 | awk '{print $1}')"
echo ""
echo "To run:"
echo "  ./$APPIMAGE_NAME"
echo ""
echo "To install system-wide:"
echo "  sudo mv $APPIMAGE_NAME /usr/local/bin/xenray"
echo ""
echo "For VPN mode (requires root):"
echo "  sudo ./$APPIMAGE_NAME"
echo ""

# Also create a standalone executable copy
echo -e "${GREEN}Creating standalone executable...${NC}"
EXEC_NAME="${APP_NAME}-${VERSION}-${ARCH}"
cp "dist/XenRay" "$EXEC_NAME"
chmod +x "$EXEC_NAME"

# Create a tarball with executable and resources
echo -e "${GREEN}Creating tarball package...${NC}"
TARBALL_NAME="${APP_NAME}-${VERSION}-${ARCH}.tar.gz"
mkdir -p "${BUILD_DIR}/package"
cp -r dist/* "${BUILD_DIR}/package/"
tar -czf "$TARBALL_NAME" -C "${BUILD_DIR}/package" .

sha256sum "$TARBALL_NAME" > "${TARBALL_NAME}.sha256"

echo ""
echo "======================================"
echo -e "${GREEN}Additional packages created:${NC}"
echo "======================================"
echo "Standalone: $EXEC_NAME"
echo "Tarball: $TARBALL_NAME"
echo ""
