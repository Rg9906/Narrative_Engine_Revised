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
        """Inspect character state for issues.

        Rules implemented:
        - Characters mentioned only once: suggestion to develop further.
        - Canonical name appears lowercase (likely common noun): note.
        """
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        for cid, entries in state.characters.items():
            # entries is a dict of StateEntry objects
            mention_entry = entries.get('mention_count')
            name_entry = entries.get('canonical_name')

            mention_count = None
            if mention_entry and getattr(mention_entry, 'current', None):
                mention_count = getattr(mention_entry.current, 'value', None)

            # Suggest developing characters only mentioned once
            try:
                if mention_count is not None and isinstance(mention_count, int) and mention_count <= 1:
                    findings.append(Finding(
                        severity='suggestion',
                        category='character',
                        title='Underdeveloped character',
                        description=f"Character '{cid}' is only mentioned {mention_count} time(s). Consider increasing presence or consolidating references.",
                        chapter=chapter,
                        evidence_ids=getattr(mention_entry.current, 'evidence_ids', []) if mention_entry and getattr(mention_entry, 'current', None) else [],
                        related_entities=[cid],
                        confidence=0.6,
                    ))
            except Exception:
                pass

            # If canonical name looks like a common noun (all lowercase), add a note
            try:
                if name_entry and getattr(name_entry, 'current', None):
                    name_val = getattr(name_entry.current, 'value', '')
                    if isinstance(name_val, str) and name_val.islower() and len(name_val) > 1:
                        findings.append(Finding(
                            severity='note',
                            category='character',
                            title='Generic character name',
                            description=f"Character '{cid}' has a canonical name '{name_val}' that looks like a common noun. Consider a more distinctive proper name if this is a named character.",
                            chapter=chapter,
                            evidence_ids=getattr(name_entry.current, 'evidence_ids', []),
                            related_entities=[cid],
                            confidence=0.5,
                        ))
            except Exception:
                pass

        return findings
