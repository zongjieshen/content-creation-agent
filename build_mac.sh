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

# Keep terminal open to see results
read -p "Press Enter to continue..."