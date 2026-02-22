"""
LectureScribe — Transcriber Module

Manages the faster-whisper model and audio buffer for chunked transcription.
Accumulates 2-second PCM chunks into 15-second windows before transcribing.
"""

import logging
import numpy as np
import time
from pathlib import Path

logger = logging.getLogger('lecturescribe')

# Sample rate expected from the extension (16kHz mono)
SAMPLE_RATE = 16000

# Transcription window size in seconds
WINDOW_SIZE_SEC = 15

# Buffer size in samples for one window
WINDOW_SIZE_SAMPLES = SAMPLE_RATE * WINDOW_SIZE_SEC


class Transcriber:
    """Whisper-based transcription engine using faster-whisper (CTranslate2)."""

    def __init__(self, model_name='base', model_dir=None):
        """
        Initialize the transcriber.

        Args:
            model_name: Whisper model size ('tiny', 'base', 'small')
            model_dir: Directory to cache/load models from
        """
        self.model_name = model_name
        self.model_dir = model_dir or str(Path.home() / '.lecturescribe' / 'models')
        self.model = None
        self.audio_buffer = np.array([], dtype=np.float32)
        self.session_start_time = time.time()
        self.total_samples_processed = 0
        self._load_model()

    def _load_model(self):
        """Load the faster-whisper model."""
        try:
            from faster_whisper import WhisperModel

            logger.info(f'Loading whisper model: {self.model_name}')
            start = time.time()

            # Use int8 quantization to reduce memory on Apple Silicon
            self.model = WhisperModel(
                self.model_name,
                device='cpu',  # faster-whisper on macOS uses CPU with Accelerate
                compute_type='int8',
                download_root=self.model_dir
            )

            elapsed = time.time() - start
            logger.info(f'Model loaded in {elapsed:.1f}s')
        except ImportError:
            logger.error('faster-whisper not installed. Run: pip install faster-whisper')
            raise
        except Exception as e:
            logger.exception(f'Failed to load whisper model: {e}')
            raise

    def process_chunk(self, audio_float32):
        """
        Add audio data to the buffer. When the buffer reaches the window size,
        transcribe it and return the result.

        Args:
            audio_float32: numpy array of float32 PCM audio samples (16kHz mono)

        Returns:
            list of segments [{'timestamp': 'HH:MM:SS', 'text': '...'}] or None
        """
        self.audio_buffer = np.concatenate([self.audio_buffer, audio_float32])

        # Only transcribe when we have a full window
        if len(self.audio_buffer) >= WINDOW_SIZE_SAMPLES:
            # Take the window and keep any remainder
            window = self.audio_buffer[:WINDOW_SIZE_SAMPLES]
            self.audio_buffer = self.audio_buffer[WINDOW_SIZE_SAMPLES:]

            return self._transcribe(window)

        return None

    def flush(self):
        """
        Transcribe any remaining audio in the buffer.

        Returns:
            list of segments or None
        """
        if len(self.audio_buffer) < SAMPLE_RATE:  # Less than 1 second, skip
            return None

        result = self._transcribe(self.audio_buffer)
        self.audio_buffer = np.array([], dtype=np.float32)
        return result

    def _transcribe(self, audio):
        """
        Run Whisper transcription on an audio segment.

        Args:
            audio: numpy float32 array of audio samples

        Returns:
            list of segments [{'timestamp': 'HH:MM:SS', 'text': '...'}]
        """
        if self.model is None:
            logger.error('Model not loaded')
            return None

        try:
            start = time.time()

            # Calculate the wall-clock offset for this segment
            segment_offset_sec = self.total_samples_processed / SAMPLE_RATE
            self.total_samples_processed += len(audio)

            # Run transcription
            segments_gen, info = self.model.transcribe(
                audio,
                language='en',
                beam_size=3,
                best_of=3,
                vad_filter=True,  # Use Whisper's built-in VAD for segment filtering
                vad_parameters={
                    'min_silence_duration_ms': 500,
                    'speech_pad_ms': 200
                }
            )

            results = []
            for segment in segments_gen:
                text = segment.text.strip()
                if text:
                    # Convert segment start time to wall-clock timestamp
                    wall_time = segment_offset_sec + segment.start
                    timestamp = self._format_timestamp(wall_time)
                    results.append({
                        'timestamp': timestamp,
                        'text': text
                    })

            elapsed = time.time() - start
            audio_duration = len(audio) / SAMPLE_RATE
            logger.info(
                f'Transcribed {audio_duration:.1f}s audio in {elapsed:.1f}s '
                f'(RTF: {elapsed/audio_duration:.2f}x) — {len(results)} segments'
            )

            return results if results else None

        except Exception as e:
            logger.exception(f'Transcription error: {e}')
            return None

    @staticmethod
    def _format_timestamp(seconds):
        """Convert seconds to HH:MM:SS format."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f'{h:02d}:{m:02d}:{s:02d}'

    def cleanup(self):
        """Release model resources."""
        self.model = None
        self.audio_buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = 0
        logger.info('Transcriber cleaned up')
