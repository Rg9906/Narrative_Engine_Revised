"""
Timeline Memory — Chronological event tracking.

Implementation: Phase 8
"""

from src.memory.base_memory import BaseMemory


class TimelineMemory(BaseMemory):
    """Manages the chronological timeline of story events."""

    def __init__(self, memory_file=None):
        super().__init__(memory_file)

    def update_from_chapter(self, chapter_data, chapter_num: int) -> list:
        """Append events to the timeline from chapter evidence.

        Phase 8 baseline:
          - For each relation extracted in the chapter, create a simple event
            entry and record it as a StateChange introduction.
          - Does not persist into `NarrativeState.timeline` (caller may append).
        """
        from typing import List
        import re

        from src.models.state import StateChange, StateChangeType, NarrativeElementType

        changes: List[StateChange] = []

        def _make_eid(idx: int) -> str:
            return f"ch{chapter_num}_evt{idx}"

        for idx, rel in enumerate(getattr(chapter_data, "relations", []), start=1):
            try:
                subj = rel.subject or ""
                pred = rel.predicate or ""
                obj = rel.object or ""
            except Exception:
                continue

            eid = _make_eid(idx)
            desc = f"{subj} {pred} {obj}".strip()

            # Record a lightweight event entry in memory entries as well
            self.update_entry(eid, "description", desc, chapter=chapter_num,
                              evidence_ids=[], confidence=0.8,
                              reasoning="Event extracted from relation evidence.")

            changes.append(
                StateChange(
                    change_type=StateChangeType.INTRODUCTION,
                    target_type=NarrativeElementType.EVENT,
                    target_id=eid,
                    field_key="description",
                    new_value=desc,
                    confidence=0.8,
                    reasoning="Timeline event created from relation.",
                )
            )

        return changes
