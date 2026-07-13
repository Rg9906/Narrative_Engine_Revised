"""
Style Memory — Tracking prose style and readability metrics.

Tracks paragraph metrics, sentence metrics, vocabulary density, and dialogue ratio.

Implementation: Phase 11
"""

from typing import Dict, List, Optional

from src.memory.base_memory import BaseMemory
from src.models.state import (
    ChapterData,
    StateChange,
    StateChangeType,
    NarrativeElementType,
)


class StyleMemory(BaseMemory):
    """Manages tracking of stylistic and readability metrics over chapters."""

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update style state from chapter metrics.

        Args:
            chapter_data: Structured evidence from the NLP pipeline.
            chapter_num: The chapter number being processed.

        Returns:
            List of StateChange objects.
        """
        changes: List[StateChange] = []
        metrics = chapter_data.style_metrics
        if not metrics:
            return changes

        # Update metrics for "global_style" entity
        entity_id = "global_style"

        for key, val in metrics.items():
            # Skip complex/nested dictionary structures (like pos_distribution) for flat comparison
            if key == "pos_distribution":
                continue

            old_entry = self.get_entry(entity_id, key)
            old_val = old_entry.current.value if old_entry and old_entry.current else None

            self.update_entry(
                entity_id,
                key,
                val,
                chapter=chapter_num,
                evidence_ids=[],
                confidence=1.0,
                reasoning=f"Extracted stylistic metric '{key}' from Chapter {chapter_num}.",
                importance=0.4,
            )

            if old_val is None:
                changes.append(
                    StateChange(
                        change_type=StateChangeType.INTRODUCTION,
                        target_type=NarrativeElementType.STYLE,
                        target_id=entity_id,
                        field_key=key,
                        new_value=val,
                        confidence=1.0,
                        reasoning=f"Style metric '{key}' tracked for the first time.",
                    )
                )
            else:
                changes.append(
                    StateChange(
                        change_type=StateChangeType.EVOLUTION,
                        target_type=NarrativeElementType.STYLE,
                        target_id=entity_id,
                        field_key=key,
                        old_value=old_val,
                        new_value=val,
                        confidence=1.0,
                        reasoning=f"Style metric '{key}' updated from {old_val} to {val}.",
                    )
                )

        return changes
