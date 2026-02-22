"""
LectureScribe — Voice Activity Detection Module

Uses Silero VAD to classify audio chunks as speech/non-speech.
Tracks consecutive silence duration for auto-stop functionality.
"""

import logging
import time
import numpy as np
from pathlib import Path

logger = logging.getLogger('lecturescribe')

# Silero VAD expects 16kHz audio
SAMPLE_RATE = 16000

# Silero VAD works with specific frame sizes (in samples)
# 512 samples = 32ms at 16kHz
VAD_FRAME_SIZE = 512


class VoiceActivityDetector:
    """Silero VAD wrapper for speech detection and silence tracking."""

    def __init__(self, silence_threshold_sec=600):
        """
        Args:
            silence_threshold_sec: Seconds of continuous silence before auto-stop
                                   (default: 600 = 10 minutes)
        """
        self.silence_threshold_sec = silence_threshold_sec
        self.model = None
        self.last_speech_time = time.time()
        self.silence_start_time = None
        self.consecutive_silence_sec = 0.0
        self.speech_probability_history = []
        self._load_model()

    def _load_model(self):
        """Load the Silero VAD ONNX model."""
        try:
            import onnxruntime as ort

            # Check for bundled model first, then download directory
            model_paths = [
                Path(__file__).parent / 'models' / 'silero_vad.onnx',
                Path.home() / '.lecturescribe' / 'models' / 'silero_vad.onnx'
            ]

            model_path = None
            for p in model_paths:
                if p.exists():
                    model_path = p
                    break

            if model_path is None:
                # Download the model
                self._download_model()
                model_path = Path.home() / '.lecturescribe' / 'models' / 'silero_vad.onnx'

            self.session = ort.InferenceSession(
                str(model_path),
                providers=['CPUExecutionProvider']
            )

            # Initialize hidden state for Silero VAD v5
            # Shape: [2, 1, 64] for LSTM hidden states
            self._h = np.zeros((2, 1, 64), dtype=np.float32)
            self._c = np.zeros((2, 1, 64), dtype=np.float32)
            self._sr = np.array([SAMPLE_RATE], dtype=np.int64)

            logger.info(f'Silero VAD loaded from {model_path}')

        except ImportError:
            logger.error('onnxruntime not installed. Run: pip install onnxruntime')
            raise

    def _download_model(self):
        """Download Silero VAD ONNX model."""
        import urllib.request

        model_dir = Path.home() / '.lecturescribe' / 'models'
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / 'silero_vad.onnx'

        url = 'https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx'
        logger.info(f'Downloading Silero VAD model from {url}')
        urllib.request.urlretrieve(url, str(model_path))
        logger.info(f'Silero VAD model saved to {model_path}')

    def process_chunk(self, audio_float32):
        """
        Process a chunk of audio through VAD.

        Args:
            audio_float32: numpy float32 array of audio samples (16kHz mono)

        Returns:
            bool: True if speech was detected in this chunk
        """
        if self.session is None:
            return True  # Assume speech if model not loaded

        speech_detected = False

        # Process in VAD_FRAME_SIZE windows
        for i in range(0, len(audio_float32) - VAD_FRAME_SIZE + 1, VAD_FRAME_SIZE):
            frame = audio_float32[i:i + VAD_FRAME_SIZE].astype(np.float32)

            # Run inference
            try:
                ort_inputs = {
                    'input': frame.reshape(1, -1),
                    'h': self._h,
                    'c': self._c,
                    'sr': self._sr
                }
                ort_outputs = self.session.run(None, ort_inputs)
                probability = ort_outputs[0].item()
                self._h = ort_outputs[1]
                self._c = ort_outputs[2]

                self.speech_probability_history.append(probability)
                # Keep only last 100 values
                if len(self.speech_probability_history) > 100:
                    self.speech_probability_history.pop(0)

                if probability > 0.5:  # Speech threshold
                    speech_detected = True

            except Exception as e:
                logger.debug(f'VAD inference error: {e}')
                continue

        # Update silence tracking
        now = time.time()

        if speech_detected:
            self.last_speech_time = now
            self.silence_start_time = None
            self.consecutive_silence_sec = 0.0
        else:
            if self.silence_start_time is None:
                self.silence_start_time = now
            self.consecutive_silence_sec = now - self.silence_start_time

        return speech_detected

    def get_silence_duration(self):
        """Get current consecutive silence duration in seconds."""
        return self.consecutive_silence_sec

    def should_auto_stop(self):
        """
        Check if the silence duration has exceeded the auto-stop threshold.

        Returns:
            bool: True if we should auto-stop
        """
        return self.consecutive_silence_sec >= self.silence_threshold_sec

    def get_average_speech_probability(self):
        """Get the average speech probability over recent frames."""
        if not self.speech_probability_history:
            return 0.0
        return sum(self.speech_probability_history) / len(self.speech_probability_history)

    def reset_silence(self):
        """Reset only the silence counter (called when Whisper finds speech).
        
        This lets Whisper override VAD — if Whisper transcribes text,
        we know speech is present even if VAD disagrees.
        """
        self.last_speech_time = time.time()
        self.silence_start_time = None
        self.consecutive_silence_sec = 0.0

    def reset(self):
        """Reset full VAD state for a new session."""
        self.reset_silence()
        self.speech_probability_history.clear()
        # Reset LSTM states
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
