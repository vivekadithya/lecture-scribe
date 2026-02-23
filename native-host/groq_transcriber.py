"""
LectureScribe — Groq Transcriber Module

Uses Groq's fast Whisper API for transcription instead of local processing.
"""

import logging
import numpy as np
import time
import io
import wave
import httpx

logger = logging.getLogger('lecturescribe')

# Sample rate expected from the extension (16kHz mono)
SAMPLE_RATE = 16000
# Transcription window size in seconds (Groq minimum charge is 10s)
WINDOW_SIZE_SEC = 15
WINDOW_SIZE_SAMPLES = SAMPLE_RATE * WINDOW_SIZE_SEC


class GroqTranscriber:
    """Whisper transcription engine using Groq's cloud API."""

    def __init__(self, api_key, model_name='whisper-large-v3', **kwargs):
        """
        Initialize the Groq transcriber.

        Args:
            api_key: Groq API key
            model_name: Groq Whisper model ('whisper-large-v3' or 'distil-whisper-large-v3-en')
            kwargs: Ignore other kwargs passed from main.py
        """
        self.api_key = api_key
        # Validate Groq model name, fallback to whisper-large-v3 if invalid or local model name passed
        valid_models = ('whisper-large-v3', 'distil-whisper-large-v3-en')
        self.model_name = model_name if model_name in valid_models else 'whisper-large-v3'
        self.audio_buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = 0
        self.client = httpx.Client(timeout=30.0)

        logger.info(f'Groq transcriber initialized with model: {self.model_name}')

    def process_chunk(self, audio_float32):
        """
        Add audio data to the buffer. When the buffer reaches the window size,
        transcribe it via Groq API and return the result.
        """
        self.audio_buffer = np.concatenate([self.audio_buffer, audio_float32])

        if len(self.audio_buffer) >= WINDOW_SIZE_SAMPLES:
            window = self.audio_buffer[:WINDOW_SIZE_SAMPLES]
            self.audio_buffer = self.audio_buffer[WINDOW_SIZE_SAMPLES:]
            return self._transcribe(window)

        return None

    def flush(self):
        """Transcribe any remaining audio in the buffer."""
        if len(self.audio_buffer) < SAMPLE_RATE:
            return None

        result = self._transcribe(self.audio_buffer)
        self.audio_buffer = np.array([], dtype=np.float32)
        return result

    def _convert_to_wav(self, audio_float32):
        """Convert float32 numpy array to a bytes object containing a valid WAV file."""
        # Convert to 16-bit PCM
        audio_int16 = (audio_float32 * 32767.0).astype(np.int16)
        
        # Write to in-memory bytes buffer
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 2 bytes per sample (16-bit)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_int16.tobytes())
            
        return wav_io.getvalue()

    def _transcribe(self, audio):
        """Send audio to Groq API and format the response."""
        if not self.api_key:
            logger.error("Groq API key not set")
            return None

        try:
            start_time = time.time()
            segment_offset_sec = self.total_samples_processed / SAMPLE_RATE
            self.total_samples_processed += len(audio)

            # Convert to WAV
            wav_bytes = self._convert_to_wav(audio)

            # Make API request
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            files = {
                "file": ("audio.wav", wav_bytes, "audio/wav")
            }
            data = {
                "model": self.model_name,
                "response_format": "verbose_json", # Request verbose_json to get segments with timestamps
                "language": "en"
            }

            response = self.client.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            
            result_json = response.json()
            
            # Format results
            results = []
            segments = result_json.get('segments', [])
            
            # If API doesn't return segments (fallback format), just return the whole text as one segment
            if not segments and result_json.get('text'):
                text = result_json['text'].strip()
                if text:
                    timestamp = self._format_timestamp(segment_offset_sec)
                    results.append({'timestamp': timestamp, 'text': text})
            else:
                for segment in segments:
                    text = segment.get('text', '').strip()
                    if text:
                        # Add relative segment start time to our continuous stream offset
                        wall_time = segment_offset_sec + segment.get('start', 0)
                        timestamp = self._format_timestamp(wall_time)
                        results.append({'timestamp': timestamp, 'text': text})

            elapsed = time.time() - start_time
            audio_duration = len(audio) / SAMPLE_RATE
            logger.info(
                f'[Groq] Transcribed {audio_duration:.1f}s audio in {elapsed:.1f}s '
                f'(RTF: {elapsed/audio_duration:.2f}x) — {len(results)} segments'
            )

            return results if results else None

        except httpx.HTTPStatusError as e:
            logger.error(f"Groq API HTTP Error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.exception(f'Groq Transcription error: {e}')
            return None

    @staticmethod
    def _format_timestamp(seconds):
        """Convert seconds to HH:MM:SS format."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f'{h:02d}:{m:02d}:{s:02d}'

    def cleanup(self):
        """Release resources."""
        self.client.close()
        self.audio_buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = 0
        logger.info('Groq Transcriber cleaned up')
