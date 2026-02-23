#!/usr/bin/env python3
"""
LectureScribe — Native Messaging Host

Entry point for the Chrome Native Messaging protocol.
Reads/writes messages via stdin/stdout with 4-byte length prefix + JSON.
"""

import sys
import struct
import json
import threading
import logging
import os
from pathlib import Path

from config import Config
from transcriber import Transcriber
from vad import VoiceActivityDetector
from session import SessionManager

# Configure logging (file-based since stdout is for Chrome messages)
LOG_DIR = Path.home() / '.lecturescribe' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / 'native-host.log'),
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('lecturescribe')


class NativeMessagingHost:
    """Chrome Native Messaging protocol handler."""

    def __init__(self):
        self.config = Config()
        self.transcriber = None
        self.vad = None
        self.session_manager = None
        self.running = True
        self._lock = threading.Lock()

    def read_message(self):
        """Read a message from stdin using Chrome's native messaging protocol."""
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length or len(raw_length) < 4:
            return None

        message_length = struct.unpack('<I', raw_length)[0]
        if message_length > 1024 * 1024:  # 1MB safety limit
            logger.error(f'Message too large: {message_length} bytes')
            return None

        message_data = sys.stdin.buffer.read(message_length)
        if len(message_data) < message_length:
            return None

        return json.loads(message_data.decode('utf-8'))

    def send_message(self, message):
        """Send a message to Chrome via stdout."""
        encoded = json.dumps(message, ensure_ascii=False).encode('utf-8')
        length = struct.pack('<I', len(encoded))

        with self._lock:
            sys.stdout.buffer.write(length)
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()

    def handle_message(self, message):
        """Route incoming messages to appropriate handlers."""
        msg_type = message.get('type')

        try:
            if msg_type == 'START_SESSION':
                self.handle_start_session(message)
            elif msg_type == 'AUDIO_CHUNK':
                self.handle_audio_chunk(message)
            elif msg_type == 'STOP_SESSION':
                self.handle_stop_session(message)
            elif msg_type == 'GET_STATUS':
                self.handle_get_status(message)
            elif msg_type == 'CONFIGURE':
                self.handle_configure(message)
            elif msg_type == 'GENERATE':
                self.handle_generate(message)
            elif msg_type == 'NOTION_EXPORT':
                self.handle_notion_export(message)
            elif msg_type == 'PICK_FOLDER':
                self.handle_pick_folder(message)
            else:
                logger.warning(f'Unknown message type: {msg_type}')
        except Exception as e:
            logger.exception(f'Error handling {msg_type}')
            self.send_message({
                'type': 'ERROR',
                'error': str(e),
                'messageType': msg_type
            })

    def handle_start_session(self, message):
        """Initialize transcriber, VAD, and session manager for a new session."""
        session_id = message.get('sessionId', 'unknown')
        logger.info(f'Starting session: {session_id}')

        # Load config
        self.config.reload()

        # Track when we last sent a silence update (throttle to every 10s)
        self._last_silence_alert_time = 0

        # Initialize components
        self.transcriber = Transcriber(
            model_name=self.config.model,
            model_dir=str(self.config.model_dir)
        )
        self.vad = VoiceActivityDetector(
            silence_threshold_sec=self.config.silence_threshold
        )
        self.session_manager = SessionManager(
            session_id=session_id,
            output_dir=str(self.config.output_dir),
            gdrive_dir=self.config.gdrive_dir,
            output_format=self.config.output_format
        )

        self.send_message({
            'type': 'STATUS',
            'status': 'session_started',
            'sessionId': session_id
        })

    def handle_audio_chunk(self, message):
        """Process an incoming audio chunk through VAD and transcription."""
        if not self.transcriber or not self.vad or not self.session_manager:
            return

        import base64
        import time
        import numpy as np

        # Decode base64 PCM Int16 audio
        audio_bytes = base64.b64decode(message.get('data', ''))
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Run VAD check
        is_speech = self.vad.process_chunk(audio_float32)

        # Feed audio to transcription buffer
        transcript_result = self.transcriber.process_chunk(audio_float32)

        # KEY FIX: If Whisper produced output, it found speech.
        # Reset VAD silence counter — Whisper is the authority on speech presence.
        if transcript_result:
            self.vad.reset_silence()

        # Re-read silence duration AFTER potential reset
        silence_duration = self.vad.get_silence_duration()

        # Check for auto-stop (only when BOTH VAD says silence AND Whisper produced nothing)
        if self.vad.should_auto_stop():
            logger.info(f'Auto-stop triggered after {silence_duration:.0f}s of silence')
            self.send_message({
                'type': 'SILENCE_ALERT',
                'silenceDuration': int(silence_duration * 1000),
                'autoStop': True
            })
            self.handle_stop_session({'sessionId': self.session_manager.session_id})
            return

        # Send silence updates throttled to every 10 seconds (not every 2s chunk)
        now = time.time()
        if silence_duration > 10 and not is_speech and (now - self._last_silence_alert_time) >= 10:
            self._last_silence_alert_time = now
            self.send_message({
                'type': 'SILENCE_ALERT',
                'silenceDuration': int(silence_duration * 1000),
                'autoStop': False
            })

        # Send transcript if available
        if transcript_result:
            segments = []
            for segment in transcript_result:
                segments.append({
                    'timestamp': segment['timestamp'],
                    'text': segment['text']
                })
                # Write to file incrementally
                self.session_manager.append_transcript(
                    segment['timestamp'], segment['text']
                )

            if segments:
                # Also send current silence duration (should be 0 after reset)
                self.send_message({
                    'type': 'TRANSCRIPT_CHUNK',
                    'segments': segments,
                    'silenceDuration': 0
                })

    def handle_stop_session(self, message):
        """Finalize the session and clean up resources."""
        session_id = message.get('sessionId', 'unknown')
        logger.info(f'Stopping session: {session_id}')

        # Flush any remaining audio in the transcription buffer
        if self.transcriber:
            final_result = self.transcriber.flush()
            if final_result and self.session_manager:
                for segment in final_result:
                    self.session_manager.append_transcript(
                        segment['timestamp'], segment['text']
                    )

        # Finalize session files
        transcript_path = None
        if self.session_manager:
            transcript_path = self.session_manager.finalize()

        # Clean up
        if self.transcriber:
            self.transcriber.cleanup()
            self.transcriber = None
        self.vad = None
        self.session_manager = None

        self.send_message({
            'type': 'SESSION_COMPLETE',
            'sessionId': session_id,
            'transcriptPath': transcript_path
        })

    def handle_get_status(self, message):
        """Return current status information."""
        self.send_message({
            'type': 'STATUS',
            'status': 'ready' if not self.transcriber else 'transcribing',
            'model': self.config.model,
            'silenceThreshold': self.config.silence_threshold
        })

    def handle_configure(self, message):
        """Update configuration settings."""
        settings = message.get('settings', {})
        if 'model' in settings:
            self.config.model = settings['model']
        if 'silenceThreshold' in settings:
            self.config.silence_threshold = int(settings['silenceThreshold'])
        if 'outputDir' in settings:
            self.config.output_dir = Path(settings['outputDir']).expanduser()
        if 'outputFormat' in settings:
            self.config.output_format = settings['outputFormat']
        if 'gdriveDir' in settings:
            self.config.gdrive_dir = settings['gdriveDir'] or None
        if 'geminiApiKey' in settings:
            self.config.gemini_api_key = settings['geminiApiKey']
        if 'notionApiKey' in settings:
            self.config.notion_api_key = settings['notionApiKey']
        if 'notionPageId' in settings:
            self.config.notion_page_id = settings['notionPageId']
        if 'geminiModel' in settings:
            self.config.gemini_model = settings['geminiModel']
        if 'defaultFeatures' in settings:
            self.config.default_features = settings['defaultFeatures']
        if 'customPrompts' in settings:
            self.config.custom_prompts = settings['customPrompts']

        self.config.save()

        self.send_message({
            'type': 'STATUS',
            'status': 'configured'
        })

    def handle_pick_folder(self, message):
        """Open macOS native folder picker dialog."""
        import subprocess
        try:
            result = subprocess.run(
                ['osascript', '-e', 'POSIX path of (choose folder with prompt "Select output directory")'],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().rstrip('/')
                logger.info(f'Folder picked: {path}')
                self.send_message({'type': 'FOLDER_PICKED', 'path': path})
            else:
                logger.info('Folder picker cancelled')
                self.send_message({'type': 'FOLDER_CANCELLED'})
        except subprocess.TimeoutExpired:
            self.send_message({'type': 'FOLDER_CANCELLED'})
        except Exception as e:
            logger.error(f'Folder picker error: {e}')
            self.send_message({'type': 'FOLDER_CANCELLED'})

    def handle_generate(self, message):
        """Generate study materials from a transcript using Gemini AI."""
        session_id = message.get('sessionId', '')
        features = message.get('features', self.config.default_features)
        custom_prompts = message.get('customPrompts', {})
        transcript_text = message.get('transcript', '')

        logger.info(f'Generating study materials for {session_id}: {features}')

        # If no transcript provided, try to read from session file
        if not transcript_text and session_id:
            transcript_path = self.config.output_dir / session_id / 'transcript.md'
            if transcript_path.exists():
                transcript_text = transcript_path.read_text(encoding='utf-8')
                logger.info(f'Read transcript from {transcript_path} ({len(transcript_text)} chars)')

        if not transcript_text:
            self.send_message({
                'type': 'ERROR',
                'error': 'No transcript available for generation',
                'messageType': 'GENERATE'
            })
            return

        # Check for Gemini API key
        api_key = message.get('geminiApiKey', '') or self.config.gemini_api_key
        if not api_key:
            self.send_message({
                'type': 'ERROR',
                'error': 'Gemini API key not configured. Add it in Settings.',
                'messageType': 'GENERATE'
            })
            return

        # Send progress update
        self.send_message({
            'type': 'GENERATION_PROGRESS',
            'status': 'starting',
            'features': features
        })

        try:
            from ai_generator import AIGenerator

            generator = AIGenerator(
                api_key=api_key,
                model_name=message.get('geminiModel', '') or self.config.gemini_model,
                custom_prompts={**self.config.custom_prompts, **custom_prompts}
            )

            results = generator.generate(transcript_text, features, custom_prompts)

            # Save results to session directory
            session_dir = self.config.output_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            saved_files = generator.save_results(results, str(session_dir))

            # ─── Extract lecture name and rename folder ─────────────
            lecture_name = self._extract_lecture_name(results, session_id)
            new_session_id = session_id  # default to original

            if lecture_name:
                slug = self._slugify(lecture_name)
                new_dir = self.config.output_dir / slug

                # Avoid collisions
                if new_dir.exists() and new_dir != session_dir:
                    slug = f'{slug}-{session_id[:10]}'
                    new_dir = self.config.output_dir / slug

                if not new_dir.exists():
                    try:
                        session_dir.rename(new_dir)
                        new_session_id = slug
                        session_dir = new_dir
                        logger.info(f'Renamed session folder to: {slug}')
                    except OSError as rename_err:
                        logger.warning(f'Could not rename folder: {rename_err}')

            # Save metadata
            import json as json_mod
            metadata = {
                'original_session_id': session_id,
                'lecture_name': lecture_name or session_id,
                'slug': new_session_id,
                'recorded_at': session_id,
                'word_count': len(transcript_text.split()),
                'features_generated': list(results.keys())
            }
            with open(session_dir / 'metadata.json', 'w') as f:
                json_mod.dump(metadata, f, indent=2)

            logger.info(f'Generation complete for {new_session_id}: {list(results.keys())}')

            self.send_message({
                'type': 'GENERATION_COMPLETE',
                'sessionId': new_session_id,
                'lectureName': lecture_name or session_id,
                'results': results,
                'savedFiles': saved_files
            })

        except Exception as e:
            logger.exception(f'Generation failed for {session_id}')
            self.send_message({
                'type': 'ERROR',
                'error': str(e),
                'messageType': 'GENERATE'
            })

    def handle_notion_export(self, message):
        """Export generated study materials to Notion."""
        session_id = message.get('sessionId', '')
        results = message.get('results', {})

        logger.info(f'Exporting to Notion for {session_id}')

        api_key = message.get('notionApiKey', '') or self.config.notion_api_key
        page_id = message.get('notionPageId', '') or self.config.notion_page_id

        if not api_key:
            self.send_message({
                'type': 'ERROR',
                'error': 'Notion API key not configured. Add it in Settings.',
                'messageType': 'NOTION_EXPORT'
            })
            return

        if not page_id:
            self.send_message({
                'type': 'ERROR',
                'error': 'Notion parent page ID not configured. Add it in Settings.',
                'messageType': 'NOTION_EXPORT'
            })
            return

        try:
            from notion_export import NotionExporter

            exporter = NotionExporter(api_key=api_key, parent_page_id=page_id)
            exported = exporter.export(session_id, results)

            logger.info(f'Notion export complete for {session_id}: {exported}')

            self.send_message({
                'type': 'NOTION_EXPORT_COMPLETE',
                'sessionId': session_id,
                'pages': exported
            })

        except Exception as e:
            logger.exception(f'Notion export failed for {session_id}')
            self.send_message({
                'type': 'ERROR',
                'error': str(e),
                'messageType': 'NOTION_EXPORT'
            })

    def _extract_lecture_name(self, results, fallback):
        """Extract a lecture name from generated results."""
        # Try summary topics first
        summary = results.get('summary', {})
        if isinstance(summary, dict):
            topics = summary.get('topics', [])
            if topics and isinstance(topics[0], dict):
                name = topics[0].get('topic', '')
                if name and len(name) > 3:
                    return name[:80]  # Cap length

            # Try first key point
            key_points = summary.get('key_points', [])
            if key_points and isinstance(key_points[0], str):
                point = key_points[0]
                if len(point) > 5:
                    # Take first sentence or first 60 chars
                    name = point.split('.')[0][:60]
                    return name

        return None

    @staticmethod
    def _slugify(text):
        """Convert text to a filesystem-safe slug."""
        import re
        slug = text.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
        slug = re.sub(r'[\s_]+', '-', slug)     # Spaces/underscores to hyphens
        slug = re.sub(r'-+', '-', slug)         # Collapse multiple hyphens
        slug = slug.strip('-')
        return slug[:80] or 'untitled'

    def run(self):
        """Main event loop: read messages from Chrome and process them."""
        logger.info('LectureScribe native host started')

        while self.running:
            try:
                message = self.read_message()
                if message is None:
                    logger.info('Stdin closed, shutting down')
                    break
                self.handle_message(message)
            except Exception as e:
                logger.exception('Fatal error in message loop')
                break

        # Cleanup on exit
        if self.transcriber:
            self.transcriber.cleanup()

        logger.info('LectureScribe native host stopped')


if __name__ == '__main__':
    host = NativeMessagingHost()
    host.run()
