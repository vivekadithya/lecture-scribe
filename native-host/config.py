"""
LectureScribe — Configuration Module

Manages persistent settings stored in ~/.lecturescribe/config.json
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger('lecturescribe')

DEFAULT_CONFIG = {
    'model': 'base',
    'silence_threshold': 600,
    'output_dir': '~/LectureScribe',
    'output_format': 'timestamped',
    'gdrive_dir': None,
    'groq_api_key': '',
    'gemini_api_key': '',
    'gemini_model': 'gemini-2.5-flash',
    'notion_api_key': '',
    'notion_page_id': '',
    'default_features': ['summary', 'flashcards', 'quiz'],
    'custom_prompts': {}
}


class Config:
    """Application configuration backed by JSON file."""

    def __init__(self):
        self.config_dir = Path.home() / '.lecturescribe'
        self.config_file = self.config_dir / 'config.json'
        self.model_dir = self.config_dir / 'models'

        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # Load or create config
        self._data = {}
        self.reload()

    def reload(self):
        """Load config from disk."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f'Failed to load config, using defaults: {e}')
                self._data = dict(DEFAULT_CONFIG)
        else:
            self._data = dict(DEFAULT_CONFIG)
            self.save()

    def save(self):
        """Save current config to disk."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._data, f, indent=2)
        except IOError as e:
            logger.error(f'Failed to save config: {e}')

    @property
    def model(self):
        return self._data.get('model', DEFAULT_CONFIG['model'])

    @model.setter
    def model(self, value):
        if value in ('tiny', 'base', 'small', 'medium'):
            self._data['model'] = value

    @property
    def silence_threshold(self):
        return self._data.get('silence_threshold', DEFAULT_CONFIG['silence_threshold'])

    @silence_threshold.setter
    def silence_threshold(self, value):
        self._data['silence_threshold'] = max(60, min(3600, int(value)))

    @property
    def output_dir(self):
        return Path(self._data.get('output_dir', DEFAULT_CONFIG['output_dir'])).expanduser()

    @output_dir.setter
    def output_dir(self, value):
        self._data['output_dir'] = str(value)

    @property
    def gdrive_dir(self):
        path = self._data.get('gdrive_dir')
        if path:
            expanded = Path(path).expanduser()
            if expanded.exists():
                return str(expanded)
        # Auto-detect Google Drive folder
        return self._detect_gdrive()

    @gdrive_dir.setter
    def gdrive_dir(self, value):
        self._data['gdrive_dir'] = value

    @property
    def groq_api_key(self):
        return self._data.get('groq_api_key', '')

    @groq_api_key.setter
    def groq_api_key(self, value):
        self._data['groq_api_key'] = value

    @property
    def output_format(self):
        return self._data.get('output_format', DEFAULT_CONFIG['output_format'])

    @output_format.setter
    def output_format(self, value):
        if value in ('timestamped', 'raw'):
            self._data['output_format'] = value

    @property
    def gemini_api_key(self):
        return self._data.get('gemini_api_key', '')

    @gemini_api_key.setter
    def gemini_api_key(self, value):
        self._data['gemini_api_key'] = value

    @property
    def gemini_model(self):
        return self._data.get('gemini_model', DEFAULT_CONFIG['gemini_model'])

    @gemini_model.setter
    def gemini_model(self, value):
        self._data['gemini_model'] = value

    @property
    def notion_api_key(self):
        return self._data.get('notion_api_key', '')

    @notion_api_key.setter
    def notion_api_key(self, value):
        self._data['notion_api_key'] = value

    @property
    def notion_page_id(self):
        return self._data.get('notion_page_id', '')

    @notion_page_id.setter
    def notion_page_id(self, value):
        self._data['notion_page_id'] = value

    @property
    def default_features(self):
        return self._data.get('default_features', DEFAULT_CONFIG['default_features'])

    @default_features.setter
    def default_features(self, value):
        valid = [f for f in value if f in ('summary', 'flashcards', 'quiz')]
        self._data['default_features'] = valid

    @property
    def custom_prompts(self):
        return self._data.get('custom_prompts', {})

    @custom_prompts.setter
    def custom_prompts(self, value):
        if isinstance(value, dict):
            self._data['custom_prompts'] = value

    def _detect_gdrive(self):
        """Auto-detect Google Drive for Desktop sync folder on macOS."""
        cloud_storage = Path.home() / 'Library' / 'CloudStorage'
        if not cloud_storage.exists():
            return None

        for entry in cloud_storage.iterdir():
            if entry.name.startswith('GoogleDrive-') and entry.is_dir():
                my_drive = entry / 'My Drive'
                if my_drive.exists():
                    logger.info(f'Auto-detected Google Drive: {my_drive}')
                    return str(my_drive)

        return None
