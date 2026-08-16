"""
Narrative State Engine — THE HEART OF THE PROJECT.

This is where evidence becomes understanding.

The NLP pipeline extracts raw observations (entities, relations, dialogue).
This engine INTERPRETS those observations into meaningful state transitions.

It asks: What does this evidence MEAN for the story?

For every piece of evidence, it determines:
  - Does this confirm something we already know? (confidence boost)
  - Does this contradict existing state? (flag inconsistency)
  - Does this introduce something new? (new character, location, theme)
  - Does this evolve existing state? (relationship shift, arc progression)
  - What are the consequences? (what should we expect next)

Implementation: Phase 6 (core), expanded in Phases 7-11
"""

from __future__ import annotations

import logging
from typing import List

from src.memory.character_memory import CharacterMemory
from src.memory.relationship_memory import RelationshipMemory
from src.memory.world_memory import WorldMemory
from src.memory.timeline_memory import TimelineMemory
from src.memory.theme_memory import ThemeMemory
from src.memory.promise_memory import PromiseMemory
from src.memory.mystery_memory import MysteryMemory
from src.memory.style_memory import StyleMemory
from src.engines.scene_engine import SceneEngine
from src.models.state import (
    ChapterData,
    Evidence,
    EvidenceType,
    ExtractedRelation,
    NarrativeState,
    NarrativeElementType,
    StateChange,
    StateChangeType,
    StateDelta,
    StateSnapshot,
    StateEntry,
)

logger = logging.getLogger("NarrativeEngine.Engines.NarrativeState")


class NarrativeStateEngine:
    """
    The central intelligence of the system.

    Takes evidence (ChapterData) and current state (NarrativeState),
    produces a delta (StateDelta), and applies it.

    State(n) = State(n-1) + Delta(chapter_n)
    """

    def __init__(self, config=None):
        self._config = config

    def process_chapter(
        self,
        chapter_data: ChapterData,
        current_state: NarrativeState,
    ) -> StateDelta:
        """
        Process chapter evidence and produce a state delta.

        This is the core reasoning method — it interprets evidence
        into narrative state transitions.

        Args:
            chapter_data: Structured evidence from the NLP pipeline.
            current_state: The current narrative state.

        Returns:
            StateDelta describing all state changes.
        """
        from src.engines.state_engine import StateEngine
        engine = StateEngine(self._config)
        delta = engine.process_chapter(chapter_data, current_state)

        # Scene detection (attach scenes to chapter evidence)
        try:
            from src.engines.scene_engine import SceneEngine
            from src.models.state import StateChange, StateChangeType, NarrativeElementType
            scene_engine = SceneEngine(self._config)
            scenes = scene_engine.detect_scenes(chapter_data.raw_text, chapter_data.chapter_number)

            character_names = set()
            for char_id, char_state in current_state.characters.items():
                name_entry = char_state.get("canonical_name")
                if name_entry and name_entry.current:
                    character_names.add(name_entry.current.value)

            # Analyze scenes with rich metadata
            analyzed_scenes = scene_engine.analyze_all_scenes(scenes, chapter_data, character_names)
            chapter_data.scenes = analyzed_scenes

            # Emit state changes for scenes
            for s in analyzed_scenes:
                delta.changes.append(
                    StateChange(
                        change_type=StateChangeType.INTRODUCTION,
                        target_type=NarrativeElementType.SCENE,
                        target_id=s.get("id"),
                        field_key="scene_text",
                        new_value=(s.get("title") or s.get("text"))[:200],
                        confidence=0.7,
                        reasoning="Scene detected by SceneEngine.",
                    )
                )
        except Exception as e:
            # Was a bare `except Exception: pass` -- any failure here (malformed scene dict,
            # a coreference-cluster attribute error, etc.) silently left chapter_data.scenes
            # unset with zero diagnostic output, and downstream inspectors relying on scenes
            # got nothing with no error surfaced anywhere. Caught by a self-review pass.
            logger.warning(f"Scene analysis failed for chapter {chapter_data.chapter_number}: {e}")

        # === Reconciliation Layer & Trait Decay ===
        delta.changes = self.reconcile_state_changes(current_state, delta)
        self.apply_confidence_decay(current_state, delta)

        # Evidence storage for all extracted relations and entities
        delta.new_evidence.extend(self._collect_evidence(chapter_data))

        # Prepare a concise summary of what the chapter contributed
        delta.summary = self._build_summary(delta)

        return delta

    def _collect_evidence(self, chapter_data: ChapterData) -> List[Evidence]:
        evidence_items: List[Evidence] = []

        for relation in chapter_data.relations:
            evidence_items.append(self._evidence_from_relation(chapter_data.chapter_number, relation))

        for entity in chapter_data.entities:
            evidence_items.append(self._evidence_from_entity(chapter_data.chapter_number, entity))

        for dialogue in chapter_data.dialogues:
            evidence_items.append(self._evidence_from_dialogue(chapter_data.chapter_number, dialogue))

        return evidence_items

    def _evidence_from_relation(self, chapter_number: int, relation: ExtractedRelation) -> Evidence:
        return Evidence(
            text_span=None,
            evidence_type=EvidenceType.ACTION if relation.predicate else EvidenceType.DIRECT_STATEMENT,
            source_chapter=chapter_number,
            confidence=relation.confidence,
            related_entities=[relation.subject, relation.object],
            interpretation_hint=f"Relation evidence: {relation.subject} {relation.predicate} {relation.object}",
        )

    def _evidence_from_entity(self, chapter_number: int, entity) -> Evidence:
        return Evidence(
            text_span=entity.span,
            evidence_type=EvidenceType.DIRECT_STATEMENT,
            source_chapter=chapter_number,
            confidence=entity.confidence,
            related_entities=[entity.text],
            interpretation_hint=f"Entity evidence: {entity.text} ({entity.label})",
        )

    def _evidence_from_dialogue(self, chapter_number: int, dialogue) -> Evidence:
        return Evidence(
            text_span=dialogue.span,
            evidence_type=EvidenceType.DIALOGUE,
            source_chapter=chapter_number,
            confidence=dialogue.confidence,
            related_entities=[dialogue.speaker],
            interpretation_hint=f"Dialogue evidence attributed to {dialogue.speaker}",
        )

    def _build_summary(self, delta: StateDelta) -> str:
        introduction_count = len([c for c in delta.changes if c.change_type == StateChangeType.INTRODUCTION])
        evolution_count = len([c for c in delta.changes if c.change_type == StateChangeType.EVOLUTION])
        confirmation_count = len([c for c in delta.changes if c.change_type == StateChangeType.CONFIRMATION])
        contradiction_count = len([c for c in delta.changes if c.change_type == StateChangeType.CONTRADICTION])

        return (
            f"Chapter {delta.chapter_number} produced {len(delta.changes)} state changes: "
            f"{introduction_count} introductions, {evolution_count} evolutions, "
            f"{confirmation_count} confirmations, {contradiction_count} contradictions. "
            f"Collected {len(delta.new_evidence)} evidence items."
        )

    def reconcile_state_changes(self, state: NarrativeState, delta: StateDelta) -> List[StateChange]:
        """
        Reconciliation Layer — cross-entity invariants only.

        Per-field contradiction detection (hair color changing, status flips, etc.) now
        happens BEFORE the write, in ValidationEngine (src/engines/validation_engine.py),
        called from StateEngine.process_chapter for LLM-authored proposals. That replaced
        what used to live here: this method historically re-read `state.characters` for the
        "old" value AFTER StateEngine had already applied every change for the chapter — so
        `existing_entry.current.value` was always already equal to `change.new_value` by the
        time this ran, making the old/new comparison here structurally unable to fire. Rather
        than keep dead code, that block is removed.

        What's left is a genuinely different kind of check: an invariant across DIFFERENT
        characters (the same item can't be in two people's inventories at once), which can
        only be checked after a chapter's changes have all landed, not per-field pre-write.
        """
        reconciled = []
        chapter_num = delta.chapter_number

        for change in delta.changes:
            # INTRODUCTION included alongside EVOLUTION/CONTRADICTION: two characters can
            # each be given the same item for the FIRST time in the same chapter (both
            # changes are type INTRODUCTION, since neither character had an inventory entry
            # before), and that dual-ownership conflict was previously never checked. Caught
            # by a self-review pass.
            if change.change_type in (StateChangeType.EVOLUTION, StateChangeType.CONTRADICTION, StateChangeType.INTRODUCTION):
                if change.target_type == NarrativeElementType.CHARACTER and change.field_key == "inventory":
                    char_id = change.target_id
                    new_val = change.new_value

                    if isinstance(new_val, list):
                        for item in new_val:
                            for other_id, other_fields in state.characters.items():
                                if other_id == char_id:
                                    continue
                                other_inv_entry = other_fields.get("inventory")
                                if other_inv_entry and other_inv_entry.current:
                                    other_inv = other_inv_entry.current.value
                                    if isinstance(other_inv, list) and item in other_inv:
                                        conflict_desc = f"Conflict: Item '{item}' is possessed by both '{char_id}' and '{other_id}' in chapter {chapter_num}."
                                        conflict_id = f"conflict_inv_{item}_{chapter_num}"
                                        logger.warning(f"Inventory Conflict: {conflict_desc}")

                                        conflict_mystery = {
                                            "mystery_text": StateEntry(key="mystery_text", element_type=NarrativeElementType.MYSTERY),
                                            "status": StateEntry(key="status", element_type=NarrativeElementType.MYSTERY),
                                            "chapter_introduced": StateEntry(key="chapter_introduced", element_type=NarrativeElementType.MYSTERY),
                                            "type": StateEntry(key="type", element_type=NarrativeElementType.MYSTERY)
                                        }
                                        conflict_mystery["mystery_text"].update(StateSnapshot(value=conflict_desc, chapter=chapter_num, confidence=1.0))
                                        conflict_mystery["status"].update(StateSnapshot(value="unresolved", chapter=chapter_num, confidence=1.0))
                                        conflict_mystery["chapter_introduced"].update(StateSnapshot(value=chapter_num, chapter=chapter_num, confidence=1.0))
                                        conflict_mystery["type"].update(StateSnapshot(value="conflict", chapter=chapter_num, confidence=1.0))
                                        state.mysteries[conflict_id] = conflict_mystery
            reconciled.append(change)
        return reconciled

    def apply_confidence_decay(self, state: NarrativeState, delta: StateDelta) -> None:
        """Decay confidence of character traits/attributes that were not updated in this chapter."""
        decay_rate = 0.02
        if self._config:
            decay_rate = self._config.get("narrative_state.decay_per_chapter", 0.02)

        updated_fields = set()
        for change in delta.changes:
            updated_fields.add((change.target_id, change.field_key))

        for char_id, char_fields in state.characters.items():
            for field_key, entry in char_fields.items():
                if field_key.startswith("physical_") or field_key in ("personality_traits", "emotional_state", "goals", "fears"):
                    if (char_id, field_key) not in updated_fields:
                        if entry.current:
                            old_conf = entry.current.confidence
                            entry.current.confidence = max(0.0, round(old_conf - decay_rate, 4))
