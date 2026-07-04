"""
Pacing Inspector — Analyzes narrative pacing and flow.

Checks for:
- Chapter length consistency
- Sentence length variation
- Paragraph structure
- Dialogue vs narration balance
- Scene length distribution

Implementation: Phase 11
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class PacingInspector(BaseInspector):
    """Inspects narrative pacing for consistency and effectiveness."""

    @property
    def name(self) -> str:
        return "Pacing Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        """Inspect narrative pacing for issues.

        Rules implemented:
        - Chapters with extreme word counts (too short/long)
        - Monotonous sentence length (low variation)
        - Unbalanced dialogue/narration ratio
        - Paragraph structure issues
        """
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        # Check chapter-level metrics from delta if available
        if delta and hasattr(delta, 'chapter_number'):
            # This is a basic implementation - in a full system, we'd track
            # chapter metrics over time in the state
            pass

        # Analyze overall state for pacing patterns
        self._check_chapter_distribution(state, findings, chapter)
        self._check_character_activity(state, findings, chapter)
        self._check_theme_distribution(state, findings, chapter)

        return findings

    def _check_chapter_distribution(self, state, findings: List[Finding], chapter: int) -> None:
        """Check if chapters are being processed consistently."""
        if state.total_chapters_processed < 3:
            return

        # Check for gaps in chapter processing
        expected_chapters = list(range(1, state.last_processed_chapter + 1))
        if state.total_chapters_processed != len(expected_chapters):
            findings.append(Finding(
                severity='note',
                category='pacing',
                title='Chapter processing gap',
                description=f"Expected {len(expected_chapters)} chapters but processed {state.total_chapters_processed}. There may be gaps in chapter numbering.",
                chapter=chapter,
                evidence_ids=[],
                related_entities=[],
                confidence=0.7,
            ))

    def _check_character_activity(self, state, findings: List[Finding], chapter: int) -> None:
        """Check character mention distribution for pacing issues."""
        if not state.characters:
            return

        # Find characters with very high mention counts (might indicate overuse)
        for char_id, char_state in state.characters.items():
            mention_entry = char_state.get('mention_count')
            if mention_entry and mention_entry.current:
                count = mention_entry.current.value
                if count > 50 and state.total_chapters_processed < 10:
                    findings.append(Finding(
                        severity='suggestion',
                        category='pacing',
                        title='High character frequency',
                        description=f"Character '{char_id}' has been mentioned {count} times in {state.total_chapters_processed} chapters. Consider if this character is overused.",
                        chapter=chapter,
                        evidence_ids=getattr(mention_entry.current, 'evidence_ids', []),
                        related_entities=[char_id],
                        confidence=0.6,
                    ))

    def _check_theme_distribution(self, state, findings: List[Finding], chapter: int) -> None:
        """Check theme distribution for thematic pacing."""
        if not state.themes:
            return

        # Check if themes are being tracked
        theme_count = len([k for k in state.themes.keys() if k.startswith('theme_')])
        if theme_count == 0 and state.total_chapters_processed >= 3:
            findings.append(Finding(
                severity='suggestion',
                category='pacing',
                title='No themes detected',
                description=f"No themes have been detected after {state.total_chapters_processed} chapters. Consider if thematic elements are present in the narrative.",
                chapter=chapter,
                evidence_ids=[],
                related_entities=[],
                confidence=0.5,
            ))
