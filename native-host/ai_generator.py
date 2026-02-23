"""
LectureScribe — AI Study Material Generator

Uses Google Gemini API to generate summaries, flashcards, and quizzes
from lecture transcripts. Supports custom prompts per feature.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger('lecturescribe')

# ─── Default Prompts ────────────────────────────────────────────

# Default prompts will be loaded from prompts.json
DEFAULT_PROMPTS = {}


class AIGenerator:
    """Generates study materials from transcripts using Google Gemini."""

    def __init__(self, api_key, model_name='gemini-2.5-flash', custom_prompts=None):
        """
        Args:
            api_key: Google Gemini API key
            model_name: Gemini model to use (e.g., 'gemini-2.0-flash')
            custom_prompts: Dict of user-modified prompts (overrides defaults)
        """
        self.api_key = api_key
        self.model_name = model_name
        self.custom_prompts = custom_prompts or {}
        self.prompts = self._load_prompts()
        self.model = None
        self._init_client()

    def _load_prompts(self):
        """Load prompts from ~/.lecturescribe/prompts.json or fallback to defaults."""
        config_dir = Path.home() / '.lecturescribe'
        user_prompts_path = config_dir / 'prompts.json'
        
        import sys
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            install_dir = Path(sys._MEIPASS)
        else:
            install_dir = Path(__file__).parent
            
        default_prompts_path = install_dir / 'prompts.json'

        # 1. Try to load from ~/.lecturescribe/prompts.json
        if user_prompts_path.exists():
            try:
                with open(user_prompts_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load user prompts from {user_prompts_path}: {e}")

        # 2. If not found or failed, try to load from installation directory
        if default_prompts_path.exists():
            try:
                with open(default_prompts_path, 'r', encoding='utf-8') as f:
                    prompts = json.load(f)
                    
                    # Also copy to ~/.lecturescribe for user editing if it doesn't exist
                    if not user_prompts_path.exists():
                        try:
                            config_dir.mkdir(parents=True, exist_ok=True)
                            with open(user_prompts_path, 'w', encoding='utf-8') as f_user:
                                json.dump(prompts, f_user, indent=2)
                            logger.info(f"Initialized user prompts at {user_prompts_path}")
                        except Exception as copy_err:
                            logger.warning(f"Could not initialize user prompts file: {copy_err}")
                            
                    return prompts
            except Exception as e:
                logger.error(f"Failed to load default prompts from {default_prompts_path}: {e}")

        # 3. Final fallback (should not happen if installation is correct)
        return {
            'summary': "Generate a summary of the transcript.",
            'flashcards': "Generate flashcards from the transcript.",
            'quiz': "Generate a quiz from the transcript."
        }

    def _init_client(self):
        """Initialize the Gemini client."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f'Gemini API client initialized ({self.model_name})')
        except ImportError:
            logger.error('google-generativeai not installed. Run: pip install google-generativeai')
            raise
        except Exception as e:
            logger.error(f'Failed to initialize Gemini client: {e}')
            raise

    def _get_prompt(self, feature):
        """Get the prompt for a feature, with user overrides applied."""
        base = self.prompts.get(feature, '')
        override = self.custom_prompts.get(feature, '')
        if override:
            # User override replaces the default entirely
            return override
        return base

    def generate(self, transcript_text, features, custom_prompts=None):
        """
        Generate study materials for the requested features.

        Args:
            transcript_text: Full transcript text
            features: List of features to generate (e.g., ['summary', 'flashcards', 'quiz'])
            custom_prompts: Optional per-request prompt overrides

        Returns:
            Dict of {feature: result_dict}
        """
        if custom_prompts:
            self.custom_prompts.update(custom_prompts)

        results = {}
        for feature in features:
            if feature not in self.prompts:
                logger.warning(f'Unknown feature: {feature}')
                continue
            try:
                result = self._generate_feature(transcript_text, feature)
                results[feature] = result
                logger.info(f'Generated {feature} successfully')
            except Exception as e:
                logger.error(f'Failed to generate {feature}: {e}')
                results[feature] = {'error': str(e)}

        return results

    def _generate_feature(self, transcript_text, feature):
        """Generate a single feature from the transcript."""
        prompt = self._get_prompt(feature)

        full_prompt = f"""{prompt}

--- LECTURE TRANSCRIPT ---
{transcript_text}
--- END TRANSCRIPT ---"""

        # Truncate very long transcripts to avoid token limits
        # Gemini 2.0 Flash supports ~1M tokens, but let's be safe
        max_chars = 500_000
        if len(full_prompt) > max_chars:
            logger.warning(f'Transcript truncated from {len(full_prompt)} to {max_chars} chars')
            # Truncate from the middle of the transcript to keep beginning and end
            excess = len(full_prompt) - max_chars
            mid = len(transcript_text) // 2
            half_excess = excess // 2
            truncated = transcript_text[:mid - half_excess] + \
                        '\n\n[... transcript truncated for length ...]\n\n' + \
                        transcript_text[mid + half_excess:]
            full_prompt = f"""{prompt}

--- LECTURE TRANSCRIPT ---
{truncated}
--- END TRANSCRIPT ---"""

        # Call Gemini
        response = self.model.generate_content(
            full_prompt,
            generation_config={
                'temperature': 0.3,
                'max_output_tokens': 8192,
                'response_mime_type': 'application/json'
            }
        )

        # Parse the JSON response
        response_text = response.text.strip()

        # Try to parse as JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if '```json' in response_text:
                json_str = response_text.split('```json')[1].split('```')[0].strip()
                return json.loads(json_str)
            elif '```' in response_text:
                json_str = response_text.split('```')[1].split('```')[0].strip()
                return json.loads(json_str)
            else:
                logger.error(f'Failed to parse JSON response for {feature}')
                raise ValueError(f'Invalid JSON response from Gemini for {feature}')

    def save_results(self, results, session_dir):
        """
        Save generated study materials to the session directory.

        Args:
            results: Dict from generate()
            session_dir: Path to the session directory

        Returns:
            Dict of {feature: file_path}
        """
        session_path = Path(session_dir)
        saved_files = {}

        for feature, data in results.items():
            if 'error' in data:
                continue

            # Save raw JSON
            json_path = session_path / f'{feature}.json'
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Save human-readable Markdown version
            md_path = session_path / f'{feature}.md'
            md_content = self._format_as_markdown(feature, data)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            saved_files[feature] = {
                'json': str(json_path),
                'markdown': str(md_path)
            }
            logger.info(f'Saved {feature} to {session_path}')

        return saved_files

    def _format_as_markdown(self, feature, data):
        """Convert structured data to readable Markdown."""
        if feature == 'summary':
            return self._format_summary_md(data)
        elif feature == 'flashcards':
            return self._format_flashcards_md(data)
        elif feature == 'quiz':
            return self._format_quiz_md(data)
        return json.dumps(data, indent=2)

    def _format_summary_md(self, data):
        """Format summary as Markdown."""
        lines = ['# Lecture Summary\n']

        if 'action_items' in data and data['action_items']:
            lines.append('## 📋 Action Items\n')
            for item in data['action_items']:
                lines.append(f'- [ ] {item}')
            lines.append('')

        if 'key_points' in data and data['key_points']:
            lines.append('## 🎯 Key Points\n')
            for point in data['key_points']:
                lines.append(f'- {point}')
            lines.append('')

        if 'topics' in data and data['topics']:
            lines.append('## 📚 Topics\n')
            for topic in data['topics']:
                lines.append(f'### {topic.get("topic", "Untitled")}\n')
                lines.append(f'{topic.get("summary", "")}\n')
                terms = topic.get('key_terms', [])
                if terms:
                    lines.append(f'**Key terms:** {", ".join(terms)}\n')

        return '\n'.join(lines)

    def _format_flashcards_md(self, data):
        """Format flashcards as Markdown."""
        lines = ['# Flashcards\n']
        cards = data.get('flashcards', [])

        for i, card in enumerate(cards, 1):
            difficulty = card.get('difficulty', 'medium')
            emoji = {'easy': '🟢', 'medium': '🟡', 'hard': '🔴'}.get(difficulty, '🟡')
            lines.append(f'### Card {i} {emoji}\n')
            lines.append(f'**Q:** {card.get("question", "")}\n')
            lines.append(f'**A:** {card.get("answer", "")}\n')
            lines.append('---\n')

        return '\n'.join(lines)

    def _format_quiz_md(self, data):
        """Format quiz as Markdown."""
        lines = ['# Practice Quiz\n']

        mcqs = data.get('multiple_choice', [])
        if mcqs:
            lines.append('## Multiple Choice\n')
            for i, q in enumerate(mcqs, 1):
                lines.append(f'**{i}.** {q.get("question", "")}\n')
                for opt in q.get('options', []):
                    lines.append(f'   {opt}')
                lines.append('')
                lines.append(f'<details><summary>Answer</summary>{q.get("correct_answer", "")} — {q.get("explanation", "")}</details>\n')

        short = data.get('short_answer', [])
        if short:
            lines.append('## Short Answer\n')
            for i, q in enumerate(short, 1):
                lines.append(f'**{i}.** {q.get("question", "")}\n')
                lines.append(f'<details><summary>Sample Answer</summary>{q.get("sample_answer", "")}</details>\n')

        tf = data.get('true_false', [])
        if tf:
            lines.append('## True or False\n')
            for i, q in enumerate(tf, 1):
                lines.append(f'**{i}.** {q.get("statement", "")}\n')
                answer = "True" if q.get('answer') else "False"
                lines.append(f'<details><summary>Answer</summary>{answer} — {q.get("explanation", "")}</details>\n')

        return '\n'.join(lines)
