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

        self.config.save()

        self.send_message({
            'type': 'STATUS',
            'status': 'configured'
        })

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
