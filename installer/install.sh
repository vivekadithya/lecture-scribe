#!/bin/bash
# ─────────────────────────────────────────────────────────────
# LectureScribe — macOS Installer
#
# Installs the native messaging host companion app.
# Supports both Google Chrome and Brave Browser.
# ─────────────────────────────────────────────────────────────

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  📝 LectureScribe Installer${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Configuration
APP_DIR="$HOME/Library/Application Support/LectureScribe"
CONFIG_DIR="$HOME/.lecturescribe"
MODEL_DIR="$CONFIG_DIR/models"
OUTPUT_DIR="$HOME/LectureScribe"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Browser native messaging host directories
CHROME_HOSTS_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
BRAVE_HOSTS_DIR="$HOME/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts"

# ─── Step 1: Check Python ────────────────────────────────────

echo -e "${YELLOW}[1/6]${NC} Checking Python installation..."

if command -v python3 &>/dev/null; then
    PYTHON=$(command -v python3)
    PY_VERSION=$($PYTHON --version 2>&1)
    echo -e "  ${GREEN}✓${NC} Found $PY_VERSION at $PYTHON"
else
    echo -e "  ${RED}✗${NC} Python 3 not found. Please install Python 3.9+ first."
    echo "  Install via Homebrew: brew install python"
    exit 1
fi

# ─── Step 2: Create directories ──────────────────────────────

echo -e "${YELLOW}[2/6]${NC} Creating directories..."

mkdir -p "$APP_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$MODEL_DIR"
mkdir -p "$OUTPUT_DIR"

echo -e "  ${GREEN}✓${NC} App directory: $APP_DIR"
echo -e "  ${GREEN}✓${NC} Config directory: $CONFIG_DIR"
echo -e "  ${GREEN}✓${NC} Output directory: $OUTPUT_DIR"

# ─── Step 3: Create virtual environment & install deps ───────

echo -e "${YELLOW}[3/6]${NC} Setting up Python virtual environment..."

VENV_DIR="$APP_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    echo -e "  ${GREEN}✓${NC} Virtual environment created"
else
    echo -e "  ${GREEN}✓${NC} Virtual environment already exists"
fi

echo -e "${YELLOW}[4/6]${NC} Installing Python dependencies..."

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/../native-host/requirements.txt"

echo -e "  ${GREEN}✓${NC} Dependencies installed (faster-whisper, onnxruntime, numpy)"

# ─── Step 4: Copy native host files ─────────────────────────

echo -e "${YELLOW}[5/6]${NC} Installing native host..."

# Copy Python source files
cp "$SCRIPT_DIR/../native-host/"*.py "$APP_DIR/"

# Create the launcher script that uses the venv
cat > "$APP_DIR/lecturescribe-host" << 'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/venv/bin/python3" "$DIR/main.py"
LAUNCHER

chmod +x "$APP_DIR/lecturescribe-host"

echo -e "  ${GREEN}✓${NC} Native host installed to $APP_DIR"

# ─── Step 5: Register native messaging host for all browsers ─

echo -e "${YELLOW}[6/6]${NC} Registering native messaging host for browsers..."

# Get the extension ID from argument or use wildcard
EXT_ID="${1:-*}"

# Function to register native host for a specific browser
register_browser() {
    local BROWSER_NAME="$1"
    local HOSTS_DIR="$2"

    mkdir -p "$HOSTS_DIR"

    cat > "$HOSTS_DIR/com.lecturescribe.host.json" << EOF
{
  "name": "com.lecturescribe.host",
  "description": "LectureScribe — Local lecture transcription engine",
  "path": "$APP_DIR/lecturescribe-host",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
EOF

    echo -e "  ${GREEN}✓${NC} Registered for $BROWSER_NAME"
}

# Detect and register for installed browsers
BROWSERS_FOUND=0

# Google Chrome
if [ -d "/Applications/Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ]; then
    register_browser "Google Chrome" "$CHROME_HOSTS_DIR"
    BROWSERS_FOUND=$((BROWSERS_FOUND + 1))
fi

# Brave Browser
if [ -d "/Applications/Brave Browser.app" ] || [ -d "$HOME/Applications/Brave Browser.app" ]; then
    register_browser "Brave Browser" "$BRAVE_HOSTS_DIR"
    BROWSERS_FOUND=$((BROWSERS_FOUND + 1))
fi

# If no browser detected, register for both as fallback
if [ "$BROWSERS_FOUND" -eq 0 ]; then
    echo -e "  ${YELLOW}!${NC} No browser auto-detected, registering for both Chrome and Brave..."
    register_browser "Google Chrome" "$CHROME_HOSTS_DIR"
    register_browser "Brave Browser" "$BRAVE_HOSTS_DIR"
fi

if [ "$EXT_ID" = "*" ]; then
    echo ""
    echo -e "  ${YELLOW}NOTE:${NC} Using wildcard extension ID."
    echo "  After loading the extension, get its ID from the extensions page"
    echo "  and re-run this installer with the ID:"
    echo ""
    echo "    ./install.sh <your-extension-id>"
    echo ""
fi

# ─── Done ────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ LectureScribe installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Next steps:"
echo "  1. Open your browser's extensions page:"
echo "     • Chrome: chrome://extensions"
echo "     • Brave:  brave://extensions"
echo "  2. Enable Developer mode → Load unpacked → select the extension/ folder"
echo "  3. Navigate to a page with a lecture video"
echo "  4. Click the LectureScribe icon and hit 'Start Transcribing'"
echo ""
echo "  The Whisper model will download automatically on first use (~150MB)."
echo "  Transcripts are saved to: $OUTPUT_DIR"
echo ""
