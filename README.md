# LectureScribe

A Chrome extension that captures tab audio during online lectures and transcribes it locally in near-real-time using Whisper AI on Apple Silicon.

## Features

- 🎙️ **Tab audio capture** — Records audio from any Chrome tab with video/audio playing
- 📝 **Near-real-time transcription** — 15-second chunked transcription using faster-whisper
- 🔇 **Smart auto-stop** — Silero VAD detects extended silence and stops automatically
- 💾 **Timestamped Markdown output** — Clean, readable transcripts saved locally
- 📂 **Google Drive integration** — Optionally sync transcripts to Google Drive
- 🔒 **100% local** — No data leaves your machine (optional Groq cloud re-transcription)

## Requirements

- **macOS** (Apple Silicon M1/M2/M3)
- **Chrome** 116+
- **Python** 3.9+
- ~300MB disk space for the whisper-base model

## Quick Start

### 1. Install the companion app

```bash
cd installer
chmod +x install.sh
./install.sh
```

### 2. Load the Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder

### 3. Update the extension ID

After loading, Chrome assigns an extension ID (shown on the extensions page).
Re-run the installer with your ID:

```bash
./installer/install.sh <your-extension-id>
```

### 4. Start transcribing

1. Navigate to your college lecture portal
2. Play a lecture video
3. Click the **LectureScribe** extension icon
4. Hit **Start Transcribing**

Transcripts are saved to `~/LectureScribe/` as timestamped Markdown files.

## Project Structure

```
lecture-scribe/
├── extension/            # Chrome extension (Manifest V3)
│   ├── manifest.json
│   ├── service-worker.js # Background orchestrator
│   ├── content-script.js # Video detection
│   ├── offscreen.html/js # Tab audio capture
│   ├── audio-processor.js# AudioWorklet for PCM extraction
│   ├── popup.html/css/js # Extension popup UI
│   └── settings.html/js  # Configuration page
├── native-host/          # Python companion app
│   ├── main.py           # Native messaging entry point
│   ├── transcriber.py    # faster-whisper integration
│   ├── vad.py            # Silero VAD silence detection
│   ├── session.py        # Session & file management
│   └── config.py         # Configuration
└── installer/
    ├── install.sh        # macOS installer
    ├── uninstall.sh      # Clean uninstall
    └── build.sh          # PyInstaller build (optional)
```

## Configuration

Open the extension settings (gear icon in popup) to configure:

| Setting | Default | Description |
|---------|---------|-------------|
| Whisper model | `base` | `base` (~300MB, good) or `small` (~700MB, great) |
| Silence threshold | 10 min | Auto-stop after this duration of silence |
| Output directory | `~/LectureScribe` | Where transcripts are saved |
| Google Drive folder | Auto-detected | For automatic cloud sync |
| Groq API key | — | Optional, for cloud re-transcription |

## Uninstall

```bash
cd installer
chmod +x uninstall.sh
./uninstall.sh
```

Then remove the extension from `chrome://extensions`.

## License

MIT
