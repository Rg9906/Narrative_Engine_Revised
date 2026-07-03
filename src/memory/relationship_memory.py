"""
Relationship Memory — Evolving inter-character relationship state.

Tracks how characters relate to each other and how those ties evolve.
Implementation: Phase 7
"""

from src.memory.base_memory import BaseMemory


class RelationshipMemory(BaseMemory):
    """Manages evolving relationship state between characters."""

    def __init__(self, memory_file=None):
        super().__init__(memory_file)

    def update_from_chapter(self, chapter_data, chapter_num: int) -> list:
        """Update relationship state from chapter evidence."""
        # TODO: Phase 7 implementation
        raise NotImplementedError("Relationship memory update — Phase 7")
