#!/bin/bash

# Path to your source image (PNG format recommended)
SOURCE_IMAGE="path/to/your/icon.png"

# Create temporary iconset directory
ICONSET_NAME="content-creation-agent.iconset"
mkdir -p "$ICONSET_NAME"

# Generate all required icon sizes
sips -z 16 16     "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_16x16.png"
sips -z 32 32     "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_16x16@2x.png"
sips -z 32 32     "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_32x32.png"
sips -z 64 64     "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_32x32@2x.png"
sips -z 128 128   "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_128x128.png"
sips -z 256 256   "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_256x256.png"
sips -z 512 512   "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_512x512.png"
sips -z 1024 1024 "$SOURCE_IMAGE" --out "$ICONSET_NAME/icon_512x512@2x.png"

# Convert the iconset to icns file
iconutil -c icns "$ICONSET_NAME" -o "content-creation-agent.icns"

# Clean up the temporary iconset directory
rm -rf "$ICONSET_NAME"

echo "Icon created successfully: content-creation-agent.icns"