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
        """Append events to the timeline from chapter evidence."""
        # TODO: Phase 8 implementation
        raise NotImplementedError("Timeline memory update — Phase 8")
