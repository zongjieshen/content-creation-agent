#!/bin/bash
echo "Building content-create-agent for macOS with PyInstaller..."

# Clean previous build if exists
if [ -d "build_mac" ]; then rm -rf "build_mac"; fi
if [ -d "dist_mac" ]; then rm -rf "dist_mac"; fi

# Run PyInstaller with the spec file and custom output directories
pyinstaller --noconfirm \
  --distpath="dist_mac" \
  --workpath="build_mac" \
  content-create-agent.spec

echo "Build completed successfully!"
echo "The executable is located at: dist_mac/content-create-agent/content-create-agent"

# Create DMG file
echo "Creating DMG installer..."

# Check if create-dmg is installed
if ! command -v create-dmg &>/dev/null; then
  echo "The 'create-dmg' tool is not installed. Installing now..."
  brew install create-dmg
fi

# Prepare folder for DMG creation
mkdir -p dist_mac/dmg
rm -rf dist_mac/dmg/*
cp -r "dist_mac/content-create-agent" dist_mac/dmg/

# Create the DMG file
create-dmg \
  --volname "Content Creation Agent" \
  --volicon "content-creation-agent.icns" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "content-create-agent" 200 190 \
  --hide-extension "content-create-agent" \
  --app-drop-link 400 190 \
  --background "background.png" \
  "dist_mac/content-creation-agent.dmg" \
  "dist_mac/dmg/"

echo "DMG creation completed successfully!"
echo "The DMG installer is located at: dist_mac/content-creation-agent.dmg"

# Keep terminal open to see results
read -p "Press Enter to continue..."