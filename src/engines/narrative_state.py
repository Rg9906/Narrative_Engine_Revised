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
        delta = StateDelta(chapter_number=chapter_data.chapter_number)

        # Phase 6: Character updates from evidence
        character_memory = CharacterMemory(existing_entries=current_state.characters)
        character_changes = character_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(character_changes)

        # Phase 9: Advanced character attribute extraction
        advanced_character_changes = character_memory.extract_advanced_attributes(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(advanced_character_changes)

        # Phase 7: Relationship updates
        relationship_memory = RelationshipMemory()
        # Load existing relationships into memory helper so updates persist
        relationship_memory.load(self._wrap_entries(current_state.relationships))
        relationship_changes = relationship_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(relationship_changes)

        # Phase 7: World updates
        world_memory = WorldMemory()
        world_memory.load(self._wrap_entries(current_state.world))
        world_changes = world_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(world_changes)

        # Phase 8: Scene detection (attach scenes to chapter evidence)
        scene_engine = SceneEngine(self._config)
        try:
            scenes = scene_engine.detect_scenes(chapter_data.raw_text, chapter_data.chapter_number)

            # Phase 12: Rich scene analysis
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
        except Exception:
            # Scene detection is best-effort
            pass

        # Phase 8: Timeline updates — append simple events to the global timeline
        timeline_memory = TimelineMemory()
        timeline_changes = timeline_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(timeline_changes)

        # Phase 10: Theme tracking
        theme_memory = ThemeMemory(existing_entries=current_state.themes)
        theme_changes = theme_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(theme_changes)

        # Phase 10: Promise and foreshadowing tracking
        promise_memory = PromiseMemory(existing_entries=current_state.promises)
        promise_changes = promise_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(promise_changes)

        # Phase 10: Mystery tracking
        mystery_memory = MysteryMemory(existing_entries=current_state.mysteries)
        mystery_changes = mystery_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(mystery_changes)

        # Phase 11: Style tracking
        style_memory = StyleMemory(existing_entries=current_state.style)
        style_changes = style_memory.update_from_chapter(chapter_data, chapter_data.chapter_number)
        delta.changes.extend(style_changes)

        # Persist memory entries back into the current NarrativeState
        try:
            current_state.characters = character_memory.entries
            current_state.relationships = relationship_memory.entries
            current_state.world = world_memory.entries
            current_state.themes = theme_memory.entries
            current_state.promises = promise_memory.entries
            current_state.mysteries = mystery_memory.entries
            current_state.style = style_memory.entries
            # Append extracted relations as simple timeline events
            for rel in getattr(chapter_data, "relations", []):
                event = {
                    "chapter": chapter_data.chapter_number,
                    "subject": getattr(rel, "subject", None),
                    "predicate": getattr(rel, "predicate", None),
                    "object": getattr(rel, "object", None),
                }
                current_state.timeline.append(event)
        except Exception:
            pass

        # Evidence storage for all extracted relations and entities
        delta.new_evidence.extend(self._collect_evidence(chapter_data))

        # Prepare a concise summary of what the chapter contributed
        delta.summary = self._build_summary(delta)

        return delta

    def _wrap_entries(self, entries: dict) -> dict:
        """Helper to supply existing serialized entries into BaseMemory._entries.

        BaseMemory expects a dict in the same shape; this provides a light passthrough.
        """
        return entries or {}

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
