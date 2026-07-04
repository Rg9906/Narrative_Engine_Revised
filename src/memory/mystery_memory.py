"""
Mystery Memory — Tracking mysteries and their resolutions.

Tracks narrative mysteries and questions across chapters:
  - Mystery extraction and question tracking
  - Clue detection and accumulation
  - Mystery resolution and revelation tracking
  - Unresolved mystery detection

Implementation: Phase 10
"""

import re
from typing import Dict, List, Optional, Set

from src.memory.base_memory import BaseMemory
from src.models.state import (
    ChapterData,
    StateChange,
    StateChangeType,
    NarrativeElementType,
)


class MysteryMemory(BaseMemory):
    """Manages mystery and question tracking with full history."""

    # Mystery/question indicators (Phase 10)
    MYSTERY_INDICATORS = [
        "who", "what", "where", "when", "why", "how",
        "mystery", "secret", "hidden", "unknown", "strange",
        "wonder", "puzzle", "riddle", "enigma", "curious",
        "don't know", "couldn't understand", "baffled", "confused",
        "what happened", "how did", "why did", "who was",
        "no one knows", "nobody knows", "remains a mystery",
    ]

    # Clue indicators (Phase 10)
    CLUE_INDICATORS = [
        "clue", "hint", "suggestion", "evidence", "sign",
        "revealed", "discovered", "found", "uncovered",
        "realized", "understood", "figured out", "saw",
        "noticed", "observed", "detected", "recognized",
    ]

    # Revelation/resolution indicators (Phase 10)
    REVELATION_INDICATORS = [
        "revealed", "truth", "secret revealed", "discovered the truth",
        "finally understood", "realized that", "it was", "the truth was",
        "uncovered", "exposed", "came to light", "became clear",
        "solved", "answer", "explanation", "solution",
    ]

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update mystery state from chapter evidence (Phase 10).

        Detects mysteries, clues, and revelations from the chapter text.

        Returns:
            List of StateChange objects describing mystery changes.
        """
        changes: List[StateChange] = []

        # Extract mysteries
        mystery_changes = self._extract_mysteries(chapter_data, chapter_num)
        changes.extend(mystery_changes)

        # Extract clues
        clue_changes = self._extract_clues(chapter_data, chapter_num)
        changes.extend(clue_changes)

        # Check for revelations
        revelation_changes = self._check_revelations(chapter_data, chapter_num)
        changes.extend(revelation_changes)

        return changes

    def _extract_mysteries(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Extract mysteries and questions from dialogue and narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            for indicator in self.MYSTERY_INDICATORS:
                if indicator in sentence_lower:
                    # Extract the mystery text
                    mystery_text = sentence.strip()

                    # Generate a unique mystery ID
                    mystery_id = f"mystery_{hash(mystery_text)}"

                    # Check if this mystery already exists
                    existing_mystery = self.get_entry(mystery_id, "mystery_text")

                    if not existing_mystery or not existing_mystery.current:
                        # New mystery
                        self.update_entry(
                            mystery_id,
                            "mystery_text",
                            mystery_text,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.6,
                            reasoning=f"Mystery extracted from text containing '{indicator}'.",
                            importance=0.85,
                        )
                        self.update_entry(
                            mystery_id,
                            "status",
                            "unresolved",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.8,
                            reasoning="New mystery marked as unresolved.",
                            importance=0.85,
                        )
                        self.update_entry(
                            mystery_id,
                            "chapter_introduced",
                            chapter_num,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=1.0,
                            reasoning="Chapter where mystery was introduced.",
                            importance=0.8,
                        )
                        self.update_entry(
                            mystery_id,
                            "clue_count",
                            0,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=1.0,
                            reasoning="Initial clue count set to zero.",
                            importance=0.6,
                        )

                        changes.append(
                            StateChange(
                                change_type=StateChangeType.INTRODUCTION,
                                target_type=NarrativeElementType.MYSTERY,
                                target_id=mystery_id,
                                field_key="mystery_text",
                                new_value=mystery_text,
                                confidence=0.6,
                                reasoning=f"New mystery detected in chapter.",
                            )
                        )
                    else:
                        # Existing mystery - confirm it's still unresolved
                        status_entry = self.get_entry(mystery_id, "status")
                        if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.CONFIRMATION,
                                    target_type=NarrativeElementType.MYSTERY,
                                    target_id=mystery_id,
                                    field_key="status",
                                    old_value="unresolved",
                                    new_value="unresolved",
                                    confidence=0.5,
                                    reasoning=f"Mystery remains unresolved.",
                                )
                            )

                    break  # Only count each sentence once

        return changes

    def _extract_clues(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Extract clues that might relate to existing mysteries."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            for indicator in self.CLUE_INDICATORS:
                if indicator in sentence_lower:
                    # Extract the clue text
                    clue_text = sentence.strip()

                    # Try to associate with existing mysteries
                    # For simplicity, we'll create a general clue entry
                    clue_id = f"clue_{hash(clue_text)}_{chapter_num}"

                    existing_clue = self.get_entry(clue_id, "clue_text")

                    if not existing_clue or not existing_clue.current:
                        # New clue
                        self.update_entry(
                            clue_id,
                            "clue_text",
                            clue_text,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.6,
                            reasoning=f"Clue extracted from text containing '{indicator}'.",
                            importance=0.7,
                        )
                        self.update_entry(
                            clue_id,
                            "chapter_found",
                            chapter_num,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=1.0,
                            reasoning="Chapter where clue was found.",
                            importance=0.7,
                        )

                        changes.append(
                            StateChange(
                                change_type=StateChangeType.INTRODUCTION,
                                target_type=NarrativeElementType.MYSTERY,
                                target_id=clue_id,
                                field_key="clue_text",
                                new_value=clue_text,
                                confidence=0.6,
                                reasoning=f"New clue detected in chapter.",
                            )
                        )

                    break  # Only count each sentence once

        return changes

    def _check_revelations(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Check if any existing mysteries are resolved."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        # Check all unresolved mysteries
        for entry_id in self._entries.keys():
            if entry_id.startswith("mystery_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    # Check for revelation indicators
                    for indicator in self.REVELATION_INDICATORS:
                        if indicator in text:
                            # Mark as resolved
                            old_status = status_entry.current.value
                            self.update_entry(
                                entry_id,
                                "status",
                                "resolved",
                                chapter=chapter_num,
                                evidence_ids=[],
                                confidence=0.7,
                                reasoning=f"Resolution detected via '{indicator}' in chapter.",
                                importance=0.9,
                            )
                            self.update_entry(
                                entry_id,
                                "chapter_resolved",
                                chapter_num,
                                chapter=chapter_num,
                                evidence_ids=[],
                                confidence=0.9,
                                reasoning="Chapter where mystery was resolved.",
                                importance=0.9,
                            )

                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.RESOLUTION,
                                    target_type=NarrativeElementType.MYSTERY,
                                    target_id=entry_id,
                                    field_key="status",
                                    old_value=old_status,
                                    new_value="resolved",
                                    confidence=0.7,
                                    reasoning=f"Mystery resolved in chapter.",
                                )
                            )
                            break

        return changes

    def get_unresolved_mysteries(self) -> List[Dict]:
        """Get all unresolved mysteries."""
        unresolved = []
        for entry_id in self._entries.keys():
            if entry_id.startswith("mystery_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    text_entry = self.get_entry(entry_id, "mystery_text")
                    chapter_entry = self.get_entry(entry_id, "chapter_introduced")
                    clue_entry = self.get_entry(entry_id, "clue_count")

                    unresolved.append({
                        "id": entry_id,
                        "text": text_entry.current.value if text_entry and text_entry.current else "",
                        "chapter_introduced": chapter_entry.current.value if chapter_entry and chapter_entry.current else 0,
                        "clue_count": clue_entry.current.value if clue_entry and clue_entry.current else 0,
                    })
        return unresolved

    def get_all_clues(self) -> List[Dict]:
        """Get all clues found so far."""
        clues = []
        for entry_id in self._entries.keys():
            if entry_id.startswith("clue_"):
                text_entry = self.get_entry(entry_id, "clue_text")
                chapter_entry = self.get_entry(entry_id, "chapter_found")

                clues.append({
                    "id": entry_id,
                    "text": text_entry.current.value if text_entry and text_entry.current else "",
                    "chapter_found": chapter_entry.current.value if chapter_entry and chapter_entry.current else 0,
                })
        return clues
