"""
Character Inspector — Checks character consistency by reasoning over state.

Implementation: Phase 10
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class CharacterInspector(BaseInspector):
    """Inspects character state for consistency, arc violations, regressions."""

    # Sentences-of-presence at or below which a recurring character reads as thinly
    # drawn. Applies to cumulative `mention_count` across all chapters processed so far.
    THIN_CHARACTER_MENTION_THRESHOLD = 3

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
        underdeveloped: List[tuple] = []

        for cid, entries in state.characters.items():
            # entries is a dict of StateEntry objects
            mention_entry = entries.get('mention_count')
            name_entry = entries.get('canonical_name')

            mention_count = None
            if mention_entry and getattr(mention_entry, 'current', None):
                mention_count = getattr(mention_entry.current, 'value', None)

            # Track thinly-drawn characters — reported as a single grouped finding below
            # rather than one finding per character, which drowned out every other finding
            # in the report once a chapter introduced more than a handful of names.
            #
            # `mention_count` is now a real count of sentences the character appears in
            # (see CharacterMemory._update_presence_counts), so the threshold can be a
            # meaningful one instead of the old `<= 1`, which fired on the point-of-view
            # character because the field then counted distinct spellings.
            #
            # A low count is only worth raising if the character has had a chance to
            # develop: someone introduced in the chapter being reviewed is *supposed* to
            # be thin. So this requires the character to have been around for at least
            # one earlier chapter.
            try:
                first_seen = self._first_chapter(entries)
                if (
                    isinstance(mention_count, int)
                    and mention_count <= self.THIN_CHARACTER_MENTION_THRESHOLD
                    and first_seen is not None
                    and chapter > first_seen
                ):
                    underdeveloped.append((cid, mention_count))
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

            # Check physical trait consistency (hair_color, eye_color, age, height, build)
            try:
                physical_traits = ['hair_color', 'eye_color', 'height', 'build', 'age']
                for trait in physical_traits:
                    trait_entry = entries.get(f"physical_{trait}")
                    if trait_entry and trait_entry.current:
                        current_val = trait_entry.current.value
                        # Check history for a different value (indicating contradiction/conflict)
                        for snapshot in trait_entry.history:
                            if snapshot.value != current_val:
                                trait_name = trait.replace("_", " ")
                                findings.append(Finding(
                                    severity='warning',
                                    category='consistency',
                                    title='Physical consistency warning',
                                    description=(
                                        f"Character '{cid}' has conflicting {trait_name} descriptions: "
                                        f"previously '{snapshot.value}' (chapter {snapshot.chapter}), "
                                        f"currently '{current_val}' (chapter {trait_entry.current.chapter})."
                                    ),
                                    chapter=chapter,
                                    evidence_ids=list(set((getattr(snapshot, 'evidence_ids', []) or []) + (getattr(trait_entry.current, 'evidence_ids', []) or []))),
                                    related_entities=[cid],
                                    confidence=0.8,
                                ))
                                break
            except Exception:
                pass

            # Inventory Teleportation Check
            try:
                inv_entry = entries.get("inventory")
                if inv_entry and inv_entry.current and isinstance(inv_entry.current.value, list):
                    char_loc_entry = entries.get("location") or entries.get("physical_location") or entries.get("current_location")
                    char_loc = char_loc_entry.current.value if char_loc_entry and char_loc_entry.current else None
                    
                    for item in inv_entry.current.value:
                        item_id = item.lower().replace(" ", "_")
                        item_world = state.world.get(item_id)
                        if item_world:
                            item_loc_entry = item_world.get("location")
                            item_owner_entry = item_world.get("owner")
                            
                            item_loc = item_loc_entry.current.value if item_loc_entry and item_loc_entry.current else None
                            item_owner = item_owner_entry.current.value if item_owner_entry and item_owner_entry.current else None
                            
                            # If the item has a known location and no owner (i.e. left in that location)
                            # but the character now has it in their inventory without being at that location
                            if item_loc and not item_owner:
                                if char_loc and char_loc != item_loc:
                                    findings.append(Finding(
                                        severity='warning',
                                        category='consistency',
                                        title='Inventory teleportation warning',
                                        description=(
                                            f"Character '{cid}' utilizes or possesses the item '{item}' in chapter {chapter}, "
                                            f"but the item was left at '{item_loc}' (chapter {item_loc_entry.current.chapter}) "
                                            f"and '{cid}' is currently at '{char_loc}'."
                                        ),
                                        chapter=chapter,
                                        evidence_ids=list(set((getattr(inv_entry.current, 'evidence_ids', []) or []) + (getattr(item_loc_entry.current, 'evidence_ids', []) or []))),
                                        related_entities=[cid, item_id],
                                        confidence=0.8,
                                    ))
            except Exception:
                pass

        if underdeveloped:
            underdeveloped.sort(key=lambda pair: pair[1])
            names = ", ".join(f"'{cid}' ({count})" for cid, count in underdeveloped)
            findings.append(Finding(
                severity='suggestion',
                category='character',
                title='Thinly-drawn recurring characters',
                description=(
                    f"{len(underdeveloped)} character(s) have persisted past the chapter they were "
                    f"introduced in but still carry very little presence on the page "
                    f"(sentence counts in parentheses): {names}. Either give them enough room to "
                    f"earn their place, or fold them into a smaller cast of better-developed roles."
                ),
                chapter=chapter,
                evidence_ids=[],
                related_entities=[cid for cid, _ in underdeveloped],
                confidence=0.6,
            ))

        return findings

    @staticmethod
    def _first_chapter(entries) -> int | None:
        """Earliest chapter any field of this character was recorded in."""
        chapters = []
        for entry in entries.values():
            history = getattr(entry, 'history', None) or []
            for snapshot in history:
                chapter = getattr(snapshot, 'chapter', None)
                if isinstance(chapter, int):
                    chapters.append(chapter)
            current = getattr(entry, 'current', None)
            current_chapter = getattr(current, 'chapter', None) if current else None
            if isinstance(current_chapter, int):
                chapters.append(current_chapter)
        return min(chapters) if chapters else None
