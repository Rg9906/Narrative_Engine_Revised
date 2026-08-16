"""
Arc Inspector — Analyzes character arc progression and consistency.

Checks for:
- Character arc stage progression
- Arc consistency (no regression without reason)
- Arc completion and resolution
- Unresolved character arcs

Implementation: Phase 11
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class ArcInspector(BaseInspector):
    """Inspects character arcs for proper progression and consistency."""

    @property
    def name(self) -> str:
        return "Arc Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        """Inspect character arcs for progression issues.

        Rules implemented:
        - Characters stuck in early arc stages
        - Arc regression (moving back to earlier stages)
        - Unresolved arcs near story end
        - Missing arc progression for major characters
        """
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        if not state.characters:
            return findings

        for char_id, char_state in state.characters.items():
            self._check_arc_progression(char_id, char_state, findings, chapter)
            self._check_arc_consistency(char_id, char_state, findings, chapter)

        # Bug fix: this check was fully implemented (and named in this method's
        # own docstring as one of the "Rules implemented") but never actually
        # called -- "unresolved arc" findings silently never fired. Caught by
        # a self-review pass; no existing test relied on the missing behavior.
        self._check_unresolved_arcs(state, findings, chapter)

        return findings

    def _check_arc_progression(self, char_id: str, char_state, findings: List[Finding], chapter: int) -> None:
        """Check if character arc is progressing appropriately."""
        arc_entry = char_state.get('arc_stage')
        mention_entry = char_state.get('mention_count')

        if not arc_entry or not arc_entry.current:
            return

        arc_stage = arc_entry.current.value
        mention_count = mention_entry.current.value if mention_entry and mention_entry.current else 0

        # Check if major character is stuck in introduction
        if mention_count >= 5 and arc_stage == "introduction":
            findings.append(Finding(
                severity='suggestion',
                category='arc',
                title='Character arc not progressing',
                description=f"Character '{char_id}' has been mentioned {mention_count} times but is still in 'introduction' arc stage. Consider if their arc should progress.",
                chapter=chapter,
                evidence_ids=getattr(arc_entry.current, 'evidence_ids', []),
                related_entities=[char_id],
                confidence=0.7,
            ))

        # Check if character is in resolution too early
        if arc_stage == "resolution" and chapter < 10:
            findings.append(Finding(
                severity='note',
                category='arc',
                title='Early arc resolution',
                description=f"Character '{char_id}' has reached 'resolution' arc stage by chapter {chapter}. This may be early depending on story length.",
                chapter=chapter,
                evidence_ids=getattr(arc_entry.current, 'evidence_ids', []),
                related_entities=[char_id],
                confidence=0.6,
            ))

    def _check_arc_consistency(self, char_id: str, char_state, findings: List[Finding], chapter: int) -> None:
        """Check for arc regression (moving back to earlier stages)."""
        arc_entry = char_state.get('arc_stage')

        if not arc_entry or not arc_entry.current or not arc_entry.history:
            return

        current_stage = arc_entry.current.value
        arc_stages_order = ["introduction", "inciting_incident", "rising_action", "crisis", "climax", "resolution"]

        # Check history for regression
        for i, snapshot in enumerate(arc_entry.history):
            if snapshot.value in arc_stages_order and current_stage in arc_stages_order:
                current_idx = arc_stages_order.index(current_stage)
                history_idx = arc_stages_order.index(snapshot.value)
                if current_idx < history_idx:
                    findings.append(Finding(
                        severity='warning',
                        category='arc',
                        title='Character arc regression',
                        description=f"Character '{char_id}' appears to have regressed from '{snapshot.value}' to '{current_stage}'. Arc regression should have narrative justification.",
                        chapter=chapter,
                        evidence_ids=getattr(arc_entry.current, 'evidence_ids', []),
                        related_entities=[char_id],
                        confidence=0.8,
                    ))
                    break

    def _check_unresolved_arcs(self, state, findings: List[Finding], chapter: int) -> None:
        """Check for unresolved character arcs near story end."""
        # This would be called when we know the story is ending
        # For now, we'll check if we're past chapter 15
        if chapter < 15:
            return

        for char_id, char_state in state.characters.items():
            arc_entry = char_state.get('arc_stage')
            mention_entry = char_state.get('mention_count')

            if not arc_entry or not arc_entry.current:
                continue

            mention_count = mention_entry.current.value if mention_entry and mention_entry.current else 0

            # Check if major character hasn't reached resolution
            if mention_count >= 10 and arc_entry.current.value != "resolution":
                findings.append(Finding(
                    severity='suggestion',
                    category='arc',
                    title='Unresolved character arc',
                    description=f"Character '{char_id}' has been mentioned {mention_count} times but hasn't reached resolution. Consider if their arc needs resolution.",
                    chapter=chapter,
                    evidence_ids=getattr(arc_entry.current, 'evidence_ids', []),
                    related_entities=[char_id],
                    confidence=0.6,
                ))
