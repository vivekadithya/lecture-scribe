# 📝 LectureScribe — Installation Guide

> **Transcribe your online lectures locally using AI — no cloud, no cost.**

LectureScribe is a browser extension that captures audio from any tab playing video/audio and transcribes it in near-real-time using Whisper AI running locally on your Mac.

---

## Requirements

- **macOS** with Apple Silicon (M1 / M2 / M3 / M4)
- **Google Chrome** or **Brave Browser**
- **Python 3.9+** (pre-installed on most Macs — check with `python3 --version`)
- ~500MB disk space (for the extension + Whisper model)

---

## Installation (5 minutes)

### Step 1: Download LectureScribe

Download and unzip the LectureScribe folder. You should see this structure:

```
lecture-scribe/
├── extension/      ← Browser extension files
├── native-host/    ← AI transcription engine (Python)
└── installer/      ← Setup scripts
```

### Step 2: Run the Installer

Open **Terminal** (search "Terminal" in Spotlight) and run:

```bash
cd /path/to/lecture-scribe
./installer/install.sh
```

> 💡 **Tip:** You can drag the `lecture-scribe` folder into Terminal after typing `cd ` to auto-fill the path.

You should see all green checkmarks ✓. The installer:
- Creates a Python virtual environment with AI dependencies
- Installs the transcription engine to `~/Library/Application Support/LectureScribe/`
- Registers the native messaging host for Chrome and/or Brave (auto-detected)

### Step 3: Load the Extension

1. Open your browser's extensions page:
   - **Chrome:** Type `chrome://extensions` in the address bar
   - **Brave:** Type `brave://extensions` in the address bar

2. Enable **Developer mode** (toggle in the top-right corner)

3. Click **"Load unpacked"**

4. Navigate to and select the `extension/` folder inside `lecture-scribe/`
   > ⚠️ If you can't see the folder, press **⌘ + Shift + .** (Command + Shift + Period) in the file picker to reveal hidden folders.

5. The LectureScribe icon (📝) should appear in your browser toolbar

### Step 4: Register your Extension ID (**required for Brave**, optional for Chrome)

After loading, your browser assigns an extension ID (shown on the extensions page — a long string like `abcdefghijklmnop...`). Copy it and re-run:

```bash
./installer/install.sh <paste-your-extension-id>
```

> ⚠️ **Brave Browser users:** This step is **mandatory**. Brave rejects wildcard extension IDs and the native host won't connect without it. Chrome users can skip this but it's recommended for security.

---

## Usage

### Starting Transcription

1. Navigate to your lecture/class page and start playing the video
2. Click the **LectureScribe** icon in your toolbar
3. Click **🎙️ Start Transcribing**
4. Transcription appears in the popup within ~15 seconds

### Stopping Transcription

- Click **⏹️ Stop** in the popup to stop manually
- Or let it **auto-stop** after the configured silence period (default: 10 minutes of no speech)

### Finding Your Transcripts

Transcripts are saved as Markdown files in:

```
~/LectureScribe/YYYY-MM-DD_HH-MM-SS/transcript.md
```

Open them with any text editor, or preview them in a Markdown viewer.

### Copying to Clipboard

Click the **📋** icon next to "Live Transcript" to copy the entire transcript to your clipboard. You can then paste it into Google Docs, Notes, or any app.

---

## Settings

Click the **⚙️** gear icon in the popup to configure:

| Setting | Options | Default |
|---------|---------|---------|
| Whisper Model | Base (faster) / Small (more accurate) | Base |
| Auto-stop threshold | 5 – 30 minutes of silence | 10 min |
| Transcript format | Timestamped / Raw text | Timestamped |
| Output directory | Any folder path | ~/LectureScribe |
| Google Drive folder | For auto-sync (optional) | Auto-detected |

---

## Troubleshooting

### "Failed to connect to companion app"
The native host isn't registered. Re-run the installer:
```bash
./installer/install.sh
```

### Extension shows no transcription after 15 seconds
Check the native host logs:
```bash
cat ~/.lecturescribe/logs/native-host.log
```

### Whisper model fails to download
Ensure you have internet access on first run. The model (~150MB) downloads from Hugging Face automatically.

### Extension doesn't detect video
Some sites use shadow DOM or custom players. Try clicking "Start Transcribing" anyway — it captures all tab audio regardless of video detection.

---

## Uninstalling

```bash
cd /path/to/lecture-scribe
./installer/uninstall.sh
```

Then remove the extension from your browser's extensions page. Your transcripts in `~/LectureScribe/` are preserved.

---

## How It Works

```
Browser Tab (video playing)
    ↓ audio captured via Chrome tabCapture API
Extension (AudioWorklet extracts 16kHz PCM)
    ↓ sends 2-second audio chunks
Native Host (Python running locally)
    ↓ buffers into 15-second windows
Whisper AI (faster-whisper, runs on Apple Silicon)
    ↓ transcribes to text
Markdown file (saved to ~/LectureScribe/)
```

Everything runs **100% locally** on your Mac. No audio leaves your machine.
