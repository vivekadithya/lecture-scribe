#!/bin/bash
# ─────────────────────────────────────────────────────────────
# LectureScribe — Uninstaller
# ─────────────────────────────────────────────────────────────

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo ""
echo "Uninstalling LectureScribe..."
echo ""

# Remove native messaging host registration
rm -f "$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.lecturescribe.host.json"
echo -e "  ${GREEN}✓${NC} Removed native messaging host"

# Remove app directory (includes venv)
rm -rf "$HOME/Library/Application Support/LectureScribe"
echo -e "  ${GREEN}✓${NC} Removed app directory"

# Remove config directory
rm -rf "$HOME/.lecturescribe"
echo -e "  ${GREEN}✓${NC} Removed config directory"

echo ""
echo -e "${GREEN}LectureScribe uninstalled.${NC}"
echo ""
echo "Note: Transcripts in ~/LectureScribe/ were NOT deleted."
echo "Delete them manually if no longer needed."
echo ""
