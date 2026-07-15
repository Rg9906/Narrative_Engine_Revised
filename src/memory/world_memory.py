"""
World Memory — Evolving world state (locations, objects, rules, lore).

Implementation: Phase 7
"""

from src.memory.base_memory import BaseMemory


class WorldMemory(BaseMemory):
    """Manages evolving world state — locations, objects, rules, cultural lore."""

    def __init__(self, memory_file=None):
        super().__init__(memory_file)

    def update_from_chapter(self, chapter_data, chapter_num: int) -> list:
        """Update world state from chapter evidence.

        Phase 7 heuristic:
          - Add or update locations and objects mentioned in `chapter_data.entities`.
          - Track `first_mentioned_chapter`, `mention_count` and basic `type`.
          - Return a list of `StateChange` describing introductions/evolutions.
        """
        from typing import List
        import re

        from src.models.state import StateChange, StateChangeType, NarrativeElementType

        changes: List[StateChange] = []

        def _idify(name: str) -> str:
            if not name:
                return ""
            nid = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
            return nid.strip("_")

        for ent in getattr(chapter_data, "entities", []):
            try:
                label = (ent.label or "").lower()
                text = ent.text or ""
            except Exception:
                continue

            if label not in ("location", "object"):
                continue

            eid = _idify(text)
            if not eid:
                continue

            existing = self.get_entity_state(eid)
            if existing is None:
                # New world element
                self.update_entry(eid, "type", label, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.9,
                                  reasoning="First mention of world element.")
                self.update_entry(eid, "first_mentioned_chapter", chapter_num, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.95,
                                  reasoning="Recorded first mention chapter.")
                self.update_entry(eid, "mention_count", 1, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.9,
                                  reasoning="First mention count.")
                changes.append(
                    StateChange(
                        change_type=StateChangeType.INTRODUCTION,
                        target_type=NarrativeElementType.OBJECT if label == "object" else NarrativeElementType.LOCATION,
                        target_id=eid,
                        field_key="type",
                        new_value=label,
                        confidence=0.9,
                        reasoning=f"New world element '{text}' introduced as {label}.",
                    )
                )
            else:
                # Existing: bump mention_count
                mentry = self.get_entry(eid, "mention_count")
                prev = mentry.current.value if mentry and mentry.current else 0
                new = prev + 1
                self.update_entry(eid, "mention_count", new, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.9,
                                  reasoning="Incremented world element mention count.")
                self.update_entry(eid, "last_mentioned_chapter", chapter_num, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.9,
                                  reasoning="Updated last mention chapter.")
                changes.append(
                    StateChange(
                        change_type=StateChangeType.CONFIRMATION,
                        target_type=NarrativeElementType.OBJECT if label == "object" else NarrativeElementType.LOCATION,
                        target_id=eid,
                        field_key="mention_count",
                        old_value=prev,
                        new_value=new,
                        confidence=0.9,
                        reasoning="World element mention confirmed and counted.",
                    )
                )

        # Extract object locations if objects and locations/containers appear in the same sentence
        objects = []
        for ent in getattr(chapter_data, "entities", []):
            label = (ent.label or "").lower()
            if label == "object":
                objects.append(ent)

        for obj in objects:
            oid = _idify(obj.text)
            for loc in getattr(chapter_data, "entities", []):
                if loc.label.lower() not in ("location", "object") or loc.text.lower() == obj.text.lower():
                    continue
                lid = _idify(loc.text)
                for sentence in chapter_data.sentences:
                    sentence_lower = sentence.lower()
                    if obj.text.lower() in sentence_lower and loc.text.lower() in sentence_lower:
                        containment_verbs = ["locked", "inside", "in", "placed", "hidden", "within", "kept", "secured", "stored"]
                        if any(v in sentence_lower for v in containment_verbs):
                            existing_loc = self.get_entry(oid, "location")
                            prev_loc = existing_loc.current.value if existing_loc and existing_loc.current else None
                            if prev_loc != lid:
                                self.update_entry(oid, "location", lid, chapter=chapter_num,
                                                  evidence_ids=[obj.span.text] if obj.span else [], confidence=0.8,
                                                  reasoning=f"Located at '{lid}' (implied by sentence: '{sentence}').")
                                changes.append(
                                    StateChange(
                                        change_type=StateChangeType.EVOLUTION if prev_loc else StateChangeType.INTRODUCTION,
                                        target_type=NarrativeElementType.OBJECT,
                                        target_id=oid,
                                        field_key="location",
                                        old_value=prev_loc,
                                        new_value=lid,
                                        confidence=0.8,
                                        reasoning=f"Object location updated to: {lid}",
                                    )
                                )
                                break

        return changes
