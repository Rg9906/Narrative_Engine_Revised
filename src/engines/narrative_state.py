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
