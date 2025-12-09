#!/bin/bash
# Create beautiful DMG installer for macOS
# Usage: ./scripts/create_dmg.sh

set -e  # Exit on error

# Configuration
APP_NAME="XenRay"
VERSION="${1:-2.0.0}"  # Use first argument as version, default to 2.0.0
DMG_NAME="${APP_NAME}-${VERSION}-macOS.dmg"
VOLUME_NAME="${APP_NAME}"
APP_PATH="dist/${APP_NAME}.app"
DMG_TEMP="temp_dmg"
DMG_BACKGROUND="assets/dmg_background.png"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "Building DMG Installer for $APP_NAME"
echo "Version: $VERSION"
echo "======================================"

# Check if app exists
if [ ! -d "$APP_PATH" ]; then
    echo -e "${RED}Error: $APP_PATH not found!${NC}"
    echo "Please run 'python build_pyinstaller.py' first"
    exit 1
fi

# Create DMG directory structure
echo -e "\n${GREEN}Creating DMG directory structure...${NC}"
mkdir -p "$DMG_TEMP"
cp -R "$APP_PATH" "$DMG_TEMP/"

# Create Applications symlink
echo -e "${GREEN}Creating Applications symlink...${NC}"
ln -s /Applications "$DMG_TEMP/Applications"

# Calculate required size
echo -e "${GREEN}Calculating DMG size...${NC}"
SIZE=$(du -sh "$DMG_TEMP" | sed 's/\([0-9\.]*\)M.*/\1/')
SIZE=$(echo "${SIZE} + 50.0" | bc)  # Add 50MB buffer

# Create temporary DMG
echo -e "${GREEN}Creating temporary DMG...${NC}"
hdiutil create -srcfolder "$DMG_TEMP" -volname "$VOLUME_NAME" -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" -format UDRW -size ${SIZE}m temp.dmg

# Mount the DMG
echo -e "${GREEN}Mounting DMG...${NC}"
MOUNT_DIR=$(hdiutil attach -readwrite -noverify -noautoopen temp.dmg | \
    egrep '^/dev/' | sed 1q | awk '{print $3}')

echo "Mounted at: $MOUNT_DIR"

# Set custom background if exists
if [ -f "$DMG_BACKGROUND" ]; then
    echo -e "${GREEN}Setting custom background...${NC}"
    mkdir -p "$MOUNT_DIR/.background"
    cp "$DMG_BACKGROUND" "$MOUNT_DIR/.background/background.png"
fi

# Set custom icon positions and window properties
echo -e "${GREEN}Configuring Finder window...${NC}"
cat > /tmp/dmg_setup.applescript <<EOF
tell application "Finder"
    tell disk "$VOLUME_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {100, 100, 700, 500}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 100
        set background picture of viewOptions to file ".background:background.png"
        
        -- Set icon positions
        set position of item "$APP_NAME.app" of container window to {150, 200}
        set position of item "Applications" of container window to {450, 200}
        
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
EOF

# Run AppleScript to configure the DMG
osascript /tmp/dmg_setup.applescript || echo -e "${YELLOW}Warning: Could not set custom layout${NC}"

# Wait for Finder to finish
sleep 3

# Unmount
echo -e "${GREEN}Unmounting DMG...${NC}"
hdiutil detach "$MOUNT_DIR"

# Convert to compressed final DMG
echo -e "${GREEN}Creating compressed final DMG...${NC}"
hdiutil convert temp.dmg -format UDZO -imagekey zlib-level=9 -o "$DMG_NAME"

# Clean up
echo -e "${GREEN}Cleaning up...${NC}"
rm -rf temp.dmg "$DMG_TEMP" /tmp/dmg_setup.applescript

# Sign the DMG (if code signing identity is available)
if security find-identity -v -p codesigning | grep -q "Developer ID Application"; then
    echo -e "${GREEN}Signing DMG...${NC}"
    codesign --force --sign "Developer ID Application" "$DMG_NAME" || \
        echo -e "${YELLOW}Warning: Could not sign DMG${NC}"
else
    echo -e "${YELLOW}Skipping code signing (no Developer ID found)${NC}"
fi

# Calculate checksum
echo -e "${GREEN}Calculating SHA256 checksum...${NC}"
shasum -a 256 "$DMG_NAME" > "${DMG_NAME}.sha256"

echo ""
echo "======================================"
echo -e "${GREEN}DMG Creation Successful!${NC}"
echo "======================================"
echo "Output: $DMG_NAME"
echo "Size: $(du -h "$DMG_NAME" | awk '{print $1}')"
echo "SHA256: $(cat ${DMG_NAME}.sha256 | awk '{print $1}')"
echo ""
echo "To test:"
echo "  open $DMG_NAME"
echo ""
echo "To notarize (requires Apple Developer Account):"
echo "  xcrun notarytool submit $DMG_NAME --apple-id YOUR_EMAIL --team-id TEAM_ID --wait"
echo ""
