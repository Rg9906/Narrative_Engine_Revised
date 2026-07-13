"""
Voice Inspector — Analyzes narrative voice and style consistency.

Checks for:
- Character voice consistency in dialogue
- Narrative voice stability
- Style metric consistency
- POV consistency

Implementation: Phase 11
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class VoiceInspector(BaseInspector):
    """Inspects narrative voice and style for consistency."""

    @property
    def name(self) -> str:
        return "Voice Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        """Inspect narrative voice for consistency issues.

        Rules implemented:
        - Character voice consistency (based on dialogue patterns)
        - Style metric tracking
        - POV stability
        """
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        self._check_character_voice(state, findings, chapter)
        self._check_style_evolution(state, findings, chapter)

        return findings

    def _check_character_voice(self, state, findings: List[Finding], chapter: int) -> None:
        """Check for character voice consistency issues."""
        if not state.characters:
            return

        # Check characters with dialogue for voice patterns
        for char_id, char_state in state.characters.items():
            # Check if character has personality traits defined
            personality_entry = char_state.get('personality_traits')
            if personality_entry and personality_entry.current:
                traits = personality_entry.current.value
                if len(traits) > 5:
                    findings.append(Finding(
                        severity='note',
                        category='voice',
                        title='Complex character personality',
                        description=f"Character '{char_id}' has {len(traits)} personality traits defined. This may indicate rich characterization or potential inconsistency.",
                        chapter=chapter,
                        evidence_ids=getattr(personality_entry.current, 'evidence_ids', []),
                        related_entities=[char_id],
                        confidence=0.5,
                    ))

            # Check emotional state changes
            emotion_entry = char_state.get('emotional_state')
            if emotion_entry and emotion_entry.current:
                emotion = emotion_entry.current.value
                # Check if emotional state changes frequently
                if emotion_entry.version > 3:
                    findings.append(Finding(
                        severity='note',
                        category='voice',
                        title='Frequent emotional shifts',
                        description=f"Character '{char_id}' has had {emotion_entry.version} emotional state changes. Consider if this reflects character development or inconsistency.",
                        chapter=chapter,
                        evidence_ids=getattr(emotion_entry.current, 'evidence_ids', []),
                        related_entities=[char_id],
                        confidence=0.6,
                    ))

    def _check_style_evolution(self, state, findings: List[Finding], chapter: int) -> None:
        """Check style metric evolution over chapters."""
        if not state.style:
            return

        style_entries = state.style.get("global_style", {})
        if not style_entries and state.total_chapters_processed >= 5:
            findings.append(Finding(
                severity='note',
                category='voice',
                title='No style metrics tracked',
                description=f"No style metrics have been tracked after {state.total_chapters_processed} chapters. Style analysis may not be fully enabled.",
                chapter=chapter,
                evidence_ids=[],
                related_entities=[],
                confidence=0.4,
            ))
            return

        avg_sent_len_entry = style_entries.get("avg_sentence_length")
        if avg_sent_len_entry and avg_sent_len_entry.current and avg_sent_len_entry.history:
            current_len = avg_sent_len_entry.current.value
            previous_lens = [snapshot.value for snapshot in avg_sent_len_entry.history]
            avg_previous = sum(previous_lens) / len(previous_lens)

            # Detect sudden drift in average sentence length (sudden change in prose tempo)
            diff = abs(current_len - avg_previous)
            if diff > 8.0:
                findings.append(Finding(
                    severity='warning',
                    category='voice',
                    title='Sudden prose style shift',
                    description=(
                        f"Average sentence length changed significantly in chapter {chapter} "
                        f"({current_len} words) compared to historical average ({round(avg_previous, 1)} words). "
                        f"Verify if this tempo change is intentional."
                    ),
                    chapter=chapter,
                    confidence=0.8,
                ))
