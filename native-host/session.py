"""
LectureScribe — Session Manager Module

Manages session files: transcript output, metadata, and file organization.
Writes transcripts incrementally (append-only) for crash safety.
"""

import logging
import json
from datetime import datetime
from pathlib import Path

logger = logging.getLogger('lecturescribe')


class SessionManager:
    """Manages session lifecycle and file output."""

    def __init__(self, session_id, output_dir='~/LectureScribe', gdrive_dir=None, output_format='timestamped'):
        """
        Args:
            session_id: Unique session identifier
            output_dir: Base output directory
            gdrive_dir: Google Drive sync folder (optional)
            output_format: 'timestamped' for [HH:MM:SS] prefix, 'raw' for plain text
        """
        self.session_id = session_id
        self.output_dir = Path(output_dir).expanduser()
        self.gdrive_dir = Path(gdrive_dir).expanduser() if gdrive_dir else None
        self.output_format = output_format

        self.start_time = datetime.now()
        self.word_count = 0
        self.segment_count = 0

        # Create session directory
        self.session_dir = self.output_dir / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.transcript_path = self.session_dir / 'transcript.md'
        self.metadata_path = self.session_dir / 'metadata.json'

        # Write transcript header
        self._write_header()

        logger.info(f'Session directory created: {self.session_dir} (format: {output_format})')

    def _write_header(self):
        """Write the Markdown header for the transcript file."""
        header = (
            f'# Lecture Transcript\n\n'
            f'**Date:** {self.start_time.strftime("%Y-%m-%d")}  \n'
            f'**Started:** {self.start_time.strftime("%H:%M:%S")}  \n'
            f'**Session ID:** {self.session_id}  \n\n'
            f'---\n\n'
        )
        with open(self.transcript_path, 'w', encoding='utf-8') as f:
            f.write(header)

    def append_transcript(self, timestamp, text):
        """
        Append a transcript line to the file.
        Uses append mode for crash safety — partial writes are recoverable.

        Args:
            timestamp: Formatted timestamp string (HH:MM:SS)
            text: Transcribed text
        """
        if self.output_format == 'raw':
            line = f'{text} '
        else:
            line = f'[{timestamp}] {text}\n\n'

        with open(self.transcript_path, 'a', encoding='utf-8') as f:
            f.write(line)

        self.word_count += len(text.split())
        self.segment_count += 1

    def finalize(self):
        """
        Finalize the session: write metadata, optionally copy to Google Drive.

        Returns:
            str: Path to the transcript file
        """
        end_time = datetime.now()
        duration = end_time - self.start_time

        # Write metadata
        metadata = {
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': int(duration.total_seconds()),
            'word_count': self.word_count,
            'segment_count': self.segment_count,
            'transcript_file': str(self.transcript_path)
        }

        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        # Append footer to transcript
        footer = (
            f'\n---\n\n'
            f'**Ended:** {end_time.strftime("%H:%M:%S")}  \n'
            f'**Duration:** {self._format_duration(duration)}  \n'
            f'**Words:** {self.word_count}  \n'
        )
        with open(self.transcript_path, 'a', encoding='utf-8') as f:
            f.write(footer)

        # Copy to Google Drive folder if configured
        if self.gdrive_dir:
            self._copy_to_gdrive()

        logger.info(
            f'Session finalized: {self.session_id} — '
            f'{self.word_count} words, {self.segment_count} segments, '
            f'{self._format_duration(duration)}'
        )

        return str(self.transcript_path)

    def _copy_to_gdrive(self):
        """Copy session files to the Google Drive sync folder."""
        import shutil

        try:
            gdrive_session_dir = self.gdrive_dir / 'LectureScribe' / self.session_id
            gdrive_session_dir.mkdir(parents=True, exist_ok=True)

            # Copy transcript and metadata
            shutil.copy2(self.transcript_path, gdrive_session_dir / 'transcript.md')
            if self.metadata_path.exists():
                shutil.copy2(self.metadata_path, gdrive_session_dir / 'metadata.json')

            logger.info(f'Session copied to Google Drive: {gdrive_session_dir}')
        except Exception as e:
            logger.error(f'Failed to copy to Google Drive: {e}')

    @staticmethod
    def _format_duration(delta):
        """Format a timedelta as HH:MM:SS."""
        total_seconds = int(delta.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f'{h:02d}:{m:02d}:{s:02d}'
