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
        """Update relationship state from chapter evidence.

        Heuristic implementation (Phase 7):
          - For each extracted relation, if both subject and object look like
            person mentions, create or update a relationship entry keyed by
            "subject_id::object_id".
          - Track `relationship_label` (best-effort from verb keywords),
            `mention_count`, and `last_interaction_chapter`.
          - Emit `StateChange` objects for introductions and evolutions.
        """
        from typing import List
        import re

        from src.models.state import (
            StateChange,
            StateChangeType,
            NarrativeElementType,
        )

        changes: List[StateChange] = []

        def _idify(name: str) -> str:
            if not name:
                return ""
            nid = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
            return nid.strip("_")

        # Simple verb->relationship mapping
        verb_map = {
            "love": "ROMANTIC",
            "kiss": "ROMANTIC",
            "marry": "ROMANTIC",
            "friend": "FRIENDSHIP",
            "help": "ALLIANCE",
            "ally": "ALLIANCE",
            "hate": "ENMITY",
            "fight": "RIVALRY",
            "argu": "RIVALRY",
            "teach": "MENTORSHIP",
        }

        for rel in getattr(chapter_data, "relations", []):
            try:
                subj = rel.subject or ""
                obj = rel.object or ""
                pred = (rel.predicate or "").lower()
            except Exception:
                continue

            sid = _idify(subj)
            oid = _idify(obj)
            if not sid or not oid or sid == oid:
                continue

            key1 = f"{sid}::{oid}"
            key2 = f"{oid}::{sid}"

            # Determine existing direction-agnostic key
            existing_key = key1 if key1 in self._entries else (key2 if key2 in self._entries else None)

            # Infer a relationship label from predicate
            rel_label = "UNKNOWN"
            for k, v in verb_map.items():
                if k in pred:
                    rel_label = v
                    break

            if existing_key is None:
                # New relationship entry
                self.update_entry(key1, "relationship_label", rel_label, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.6,
                                  reasoning=f"Observed relation '{pred}' between {subj} and {obj}.")
                self.update_entry(key1, "mention_count", 1, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.8,
                                  reasoning="First observed interaction this chapter.")
                self.update_entry(key1, "last_interaction_chapter", chapter_num, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.9,
                                  reasoning="Recorded last interaction chapter.")
                changes.append(
                    StateChange(
                        change_type=StateChangeType.INTRODUCTION,
                        target_type=NarrativeElementType.CHARACTER,
                        target_id=key1,
                        field_key="relationship_label",
                        new_value=rel_label,
                        confidence=0.6,
                        reasoning=f"New relationship observed between {subj} and {obj}.",
                    )
                )
            else:
                # Update existing
                mention_entry = self.get_entry(existing_key, "mention_count")
                prev_count = mention_entry.current.value if mention_entry and mention_entry.current else 0
                new_count = prev_count + 1
                self.update_entry(existing_key, "mention_count", new_count, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.85,
                                  reasoning="Incremented mention count for relationship.")
                self.update_entry(existing_key, "last_interaction_chapter", chapter_num, chapter=chapter_num,
                                  evidence_ids=[], confidence=0.9,
                                  reasoning="Updated last interaction chapter.")
                # Possibly evolve label if new evidence stronger
                label_entry = self.get_entry(existing_key, "relationship_label")
                old_label = label_entry.current.value if label_entry and label_entry.current else None
                if rel_label != "UNKNOWN" and rel_label != old_label:
                    self.update_entry(existing_key, "relationship_label", rel_label, chapter=chapter_num,
                                      evidence_ids=[], confidence=0.7,
                                      reasoning="Updated relationship label based on verb evidence.")
                    changes.append(
                        StateChange(
                            change_type=StateChangeType.EVOLUTION,
                            target_type=NarrativeElementType.CHARACTER,
                            target_id=existing_key,
                            field_key="relationship_label",
                            old_value=old_label,
                            new_value=rel_label,
                            confidence=0.7,
                            reasoning="Relationship label evolved from new evidence.",
                        )
                    )
                else:
                    changes.append(
                        StateChange(
                            change_type=StateChangeType.CONFIRMATION,
                            target_type=NarrativeElementType.CHARACTER,
                            target_id=existing_key,
                            field_key="mention_count",
                            old_value=prev_count,
                            new_value=new_count,
                            confidence=0.85,
                            reasoning="Relationship mention confirmed and counted.",
                        )
                    )

        return changes
