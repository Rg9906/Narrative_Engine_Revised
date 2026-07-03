"""
Character Inspector — Checks character consistency by reasoning over state.

Implementation: Phase 10
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class CharacterInspector(BaseInspector):
    """Inspects character state for consistency, arc violations, regressions."""

    @property
    def name(self) -> str:
        return "Character Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        """Inspect character state for issues."""
        # TODO: Phase 10 implementation
        return []
