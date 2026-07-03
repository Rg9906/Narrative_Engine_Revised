"""
Character Memory — Evolving character state.

Tracks character profiles with versioned history:
  - Identity (names, aliases)
  - Physical traits
  - Personality traits
  - Emotional state (evolving)
  - Goals, fears, motivations
  - Arc progression

Implementation: Phase 6
"""

import re
from typing import Dict, List, Optional, Tuple

from src.memory.base_memory import BaseMemory
from src.models.state import (
    ChapterData,
    Evidence,
    ExtractedDialogue,
    ExtractedEntity,
    ExtractedRelation,
    NarrativeElementType,
    StateChange,
    StateChangeType,
)


class CharacterMemory(BaseMemory):
    """Manages evolving character state with full history and evidence."""

    PRONOUNS = {
        "i", "me", "you", "he", "him", "she", "her", "they", "them",
        "we", "us", "it", "its", "his", "hers", "their", "theirs",
    }

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def load_entries(self, entries: Dict[str, Dict[str, object]]) -> None:
        """Load existing character entries into the memory helper."""
        if entries is not None:
            self._entries = entries

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update character state from chapter evidence.

        This interprets raw evidence (entities, dialogue, actions) into
        meaningful character state transitions.

        Returns:
            List of StateChange objects describing what changed.
        """
        changes: List[StateChange] = []
        coref_map = self._build_coref_map(chapter_data)
        mentions = self._collect_character_mentions(chapter_data, coref_map)

        for mention_text in mentions:
            char_id = self._normalize_entity_id(mention_text)
            if not char_id:
                continue

            alias = mention_text.strip()
            canonical_name = alias
            existing_entity = self.get_entity_state(char_id)
            introduction = existing_entity is None

            # Update canonical name if this is the first mention.
            if introduction:
                self.update_entry(
                    char_id,
                    "canonical_name",
                    canonical_name,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="First observed mention of character.",
                    importance=0.9,
                )
                self.update_entry(
                    char_id,
                    "aliases",
                    [canonical_name],
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="Initial alias list created from first mention.",
                )
                self.update_entry(
                    char_id,
                    "last_seen_chapter",
                    chapter_num,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="Character seen in current chapter.",
                )
                self.update_entry(
                    char_id,
                    "mention_count",
                    1,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="First mention observed this chapter.",
                )
                changes.append(
                    StateChange(
                        change_type=StateChangeType.INTRODUCTION,
                        target_type=NarrativeElementType.CHARACTER,
                        target_id=char_id,
                        field_key="canonical_name",
                        new_value=canonical_name,
                        confidence=1.0,
                        reasoning="New character introduced from chapter evidence.",
                    )
                )
                continue

            # Existing character: update alias list if needed.
            alias_entry = self.get_entry(char_id, "aliases")
            if alias_entry and alias not in alias_entry.current.value:
                new_aliases = list(alias_entry.current.value) + [alias]
                self.update_entry(
                    char_id,
                    "aliases",
                    new_aliases,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.85,
                    reasoning="New alias observed for existing character.",
                )
                changes.append(
                    StateChange(
                        change_type=StateChangeType.EVOLUTION,
                        target_type=NarrativeElementType.CHARACTER,
                        target_id=char_id,
                        field_key="aliases",
                        old_value=alias_entry.current.value,
                        new_value=new_aliases,
                        confidence=0.85,
                        reasoning="Alias list expanded from chapter evidence.",
                    )
                )

            # Always refresh last seen and mention count for existing characters.
            last_seen_entry = self.get_entry(char_id, "last_seen_chapter")
            if last_seen_entry is None or last_seen_entry.current.value != chapter_num:
                self.update_entry(
                    char_id,
                    "last_seen_chapter",
                    chapter_num,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.9,
                    reasoning="Character observed in current chapter.",
                )

            mention_count_entry = self.get_entry(char_id, "mention_count")
            previous_count = mention_count_entry.current.value if mention_count_entry and mention_count_entry.current else 0
            new_count = previous_count + 1
            self.update_entry(
                char_id,
                "mention_count",
                new_count,
                chapter=chapter_num,
                evidence_ids=[],
                confidence=0.9,
                reasoning="Mention count incremented for observed character.",
            )
            changes.append(
                StateChange(
                    change_type=StateChangeType.CONFIRMATION,
                    target_type=NarrativeElementType.CHARACTER,
                    target_id=char_id,
                    field_key="mention_count",
                    old_value=previous_count,
                    new_value=new_count,
                    confidence=0.9,
                    reasoning="Existing character mention confirmed and tracked.",
                )
            )

        return changes

    def _build_coref_map(self, chapter_data: ChapterData) -> Dict[str, str]:
        """Map coreference mentions to canonical phrase strings."""
        mapping: Dict[str, str] = {}
        for cluster in chapter_data.coreference_clusters:
            canonical = next(
                (mention for mention in cluster if mention.strip().lower() not in self.PRONOUNS),
                cluster[0] if cluster else "",
            )
            canonical = canonical.strip()
            for mention in cluster:
                mapping[mention.strip()] = canonical
        return mapping

    def _collect_character_mentions(
        self,
        chapter_data: ChapterData,
        coref_map: Dict[str, str],
    ) -> List[str]:
        """Collect character mention texts from chapter evidence."""
        mentions: List[str] = []
        seen: set = set()

        def add(text: str) -> None:
            if not text or not text.strip():
                return
            text = text.strip()
            normalized = text.lower()
            if normalized in self.PRONOUNS:
                return
            text = coref_map.get(text, text)
            normalized = text.lower()
            if normalized in seen:
                return
            seen.add(normalized)
            mentions.append(text)

        for entity in chapter_data.entities:
            if entity.label.lower() == "person":
                add(entity.text)

        for relation in chapter_data.relations:
            add(relation.subject)
            add(relation.object)

        for dialogue in chapter_data.dialogues:
            if dialogue.speaker and dialogue.speaker.strip().lower() != "unknown":
                add(dialogue.speaker)

        return mentions

    def _normalize_entity_id(self, text: str) -> str:
        """Normalize a mention into a stable character identifier."""
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text
