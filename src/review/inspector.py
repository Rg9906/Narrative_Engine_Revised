"""
Base Inspector — Foundation for all editorial inspectors.

Inspectors reason over NARRATIVE STATE, not raw text.
Each inspector checks one aspect of the narrative and returns findings.

Implementation: Phase 10
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Finding:
    """A single editorial finding from an inspector."""
    severity: str          # "error", "warning", "suggestion", "note"
    category: str          # What aspect (consistency, pacing, character, etc.)
    title: str             # Brief description
    description: str       # Detailed explanation
    chapter: int           # Which chapter this relates to
    evidence_ids: List[str] = field(default_factory=list)
    related_entities: List[str] = field(default_factory=list)
    confidence: float = 1.0


class BaseInspector(ABC):
    """
    Base class for all editorial inspectors.

    Each inspector examines one aspect of the narrative state and
    produces findings. It does NOT re-read chapter text — it reasons
    over the structured, evolving state.
    """

    @abstractmethod
    def inspect(self, state, delta) -> List[Finding]:
        """
        Inspect narrative state and produce findings.

        Args:
            state: Current NarrativeState.
            delta: StateDelta from the current chapter.

        Returns:
            List of Finding objects.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this inspector."""
        pass
