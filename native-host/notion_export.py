"""
LectureScribe — Notion Export Module

Exports generated study materials to Notion using the Notion API.
Creates formatted pages with rich blocks for summaries, flashcards, and quizzes.
"""

import json
import logging

logger = logging.getLogger('lecturescribe')


class NotionExporter:
    """Exports study materials to Notion workspace."""

    def __init__(self, api_key, parent_page_id):
        """
        Args:
            api_key: Notion integration token
            parent_page_id: ID of the parent page to create sub-pages under
        """
        self.api_key = api_key
        self.parent_page_id = parent_page_id
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize the Notion client."""
        try:
            from notion_client import Client
            self.client = Client(auth=self.api_key)
            logger.info('Notion client initialized')
        except ImportError:
            logger.error('notion-client not installed. Run: pip install notion-client')
            raise

    def export(self, session_id, results):
        """
        Export study materials to Notion.

        Args:
            session_id: Session identifier (used in page title)
            results: Dict from AIGenerator.generate()

        Returns:
            Dict of {feature: notion_page_url}
        """
        exported = {}

        for feature, data in results.items():
            if 'error' in data:
                continue

            try:
                title = f"LectureScribe — {feature.title()} ({session_id})"
                blocks = self._build_blocks(feature, data)

                page = self.client.pages.create(
                    parent={"page_id": self.parent_page_id},
                    properties={
                        "title": [{"text": {"content": title}}]
                    },
                    children=blocks[:100]  # Notion limits to 100 blocks per request
                )

                page_url = page.get('url', '')
                exported[feature] = page_url
                logger.info(f'Exported {feature} to Notion: {page_url}')

                # If more than 100 blocks, append in batches
                if len(blocks) > 100:
                    page_id = page['id']
                    for i in range(100, len(blocks), 100):
                        batch = blocks[i:i + 100]
                        self.client.blocks.children.append(
                            block_id=page_id,
                            children=batch
                        )

            except Exception as e:
                logger.error(f'Failed to export {feature} to Notion: {e}')
                exported[feature] = {'error': str(e)}

        return exported

    def _build_blocks(self, feature, data):
        """Build Notion blocks for a feature."""
        if feature == 'summary':
            return self._summary_blocks(data)
        elif feature == 'flashcards':
            return self._flashcard_blocks(data)
        elif feature == 'quiz':
            return self._quiz_blocks(data)
        return []

    def _summary_blocks(self, data):
        """Build Notion blocks for a summary."""
        blocks = []

        # Action Items
        action_items = data.get('action_items', [])
        if action_items:
            blocks.append(self._heading2('📋 Action Items'))
            for item in action_items:
                blocks.append(self._to_do(item))

        # Key Points
        key_points = data.get('key_points', [])
        if key_points:
            blocks.append(self._heading2('🎯 Key Points'))
            for point in key_points:
                blocks.append(self._bulleted_list(point))

        # Topics
        topics = data.get('topics', [])
        if topics:
            blocks.append(self._heading2('📚 Topics'))
            for topic in topics:
                blocks.append(self._heading3(topic.get('topic', 'Untitled')))
                blocks.append(self._paragraph(topic.get('summary', '')))
                terms = topic.get('key_terms', [])
                if terms:
                    blocks.append(self._paragraph(
                        f"Key terms: {', '.join(terms)}",
                        bold=True
                    ))

        return blocks

    def _flashcard_blocks(self, data):
        """Build Notion blocks for flashcards (using toggle blocks)."""
        blocks = [self._heading2('🃏 Flashcards')]

        for i, card in enumerate(data.get('flashcards', []), 1):
            difficulty = card.get('difficulty', 'medium')
            emoji = {'easy': '🟢', 'medium': '🟡', 'hard': '🔴'}.get(difficulty, '🟡')
            question = card.get('question', '')
            answer = card.get('answer', '')

            # Toggle block: question is visible, answer is hidden
            blocks.append({
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"text": {"content": f"{emoji} Q{i}: {question}"}}],
                    "children": [
                        self._paragraph(f"A: {answer}")
                    ]
                }
            })

        return blocks

    def _quiz_blocks(self, data):
        """Build Notion blocks for quiz questions."""
        blocks = []

        # Multiple Choice
        mcqs = data.get('multiple_choice', [])
        if mcqs:
            blocks.append(self._heading2('📝 Multiple Choice'))
            for i, q in enumerate(mcqs, 1):
                blocks.append(self._paragraph(f"{i}. {q.get('question', '')}"))
                for opt in q.get('options', []):
                    blocks.append(self._bulleted_list(opt))
                blocks.append({
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"text": {"content": "💡 Show Answer"}}],
                        "children": [
                            self._paragraph(
                                f"{q.get('correct_answer', '')} — {q.get('explanation', '')}"
                            )
                        ]
                    }
                })

        # Short Answer
        short = data.get('short_answer', [])
        if short:
            blocks.append(self._heading2('✏️ Short Answer'))
            for i, q in enumerate(short, 1):
                blocks.append(self._paragraph(f"{i}. {q.get('question', '')}"))
                blocks.append({
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"text": {"content": "💡 Sample Answer"}}],
                        "children": [
                            self._paragraph(q.get('sample_answer', ''))
                        ]
                    }
                })

        # True/False
        tf = data.get('true_false', [])
        if tf:
            blocks.append(self._heading2('✅ True or False'))
            for i, q in enumerate(tf, 1):
                blocks.append(self._paragraph(f"{i}. {q.get('statement', '')}"))
                answer = "True ✅" if q.get('answer') else "False ❌"
                blocks.append({
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"text": {"content": "💡 Show Answer"}}],
                        "children": [
                            self._paragraph(
                                f"{answer} — {q.get('explanation', '')}"
                            )
                        ]
                    }
                })

        return blocks

    # ─── Block Helpers ──────────────────────────────────────────

    @staticmethod
    def _heading2(text):
        return {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": text}}]
            }
        }

    @staticmethod
    def _heading3(text):
        return {
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"text": {"content": text}}]
            }
        }

    @staticmethod
    def _paragraph(text, bold=False):
        annotations = {"bold": True} if bold else {}
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "text": {"content": text},
                    "annotations": annotations
                }]
            }
        }

    @staticmethod
    def _bulleted_list(text):
        return {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"text": {"content": text}}]
            }
        }

    @staticmethod
    def _to_do(text, checked=False):
        return {
            "type": "to_do",
            "to_do": {
                "rich_text": [{"text": {"content": text}}],
                "checked": checked
            }
        }
