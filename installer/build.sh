#!/bin/bash
# ─────────────────────────────────────────────────────────────
# LectureScribe — PyInstaller Build Script
#
# Builds the native host into a standalone macOS binary.
# This is for distribution; development uses the venv launcher.
# ─────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST_DIR="$SCRIPT_DIR/../native-host"
DIST_DIR="$SCRIPT_DIR/dist"

echo "Building LectureScribe native host binary..."

# Ensure PyInstaller is available
pip install pyinstaller 2>/dev/null

# Build single-file binary
pyinstaller \
    --onefile \
    --name lecturescribe-host \
    --distpath "$DIST_DIR" \
    --workpath "$SCRIPT_DIR/build" \
    --specpath "$SCRIPT_DIR" \
    --add-data "$HOST_DIR/models:models" \
    --hidden-import faster_whisper \
    --hidden-import onnxruntime \
    --noupx \
    --clean \
    "$HOST_DIR/main.py"

echo ""
echo "Build complete: $DIST_DIR/lecturescribe-host"
echo "Binary size: $(du -sh "$DIST_DIR/lecturescribe-host" | cut -f1)"
