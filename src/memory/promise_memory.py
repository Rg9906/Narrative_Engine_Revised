"""
Promise Memory — Tracking promises, foreshadowing, and resolutions.

Tracks narrative promises and foreshadowing across chapters:
  - Promise extraction and speaker/listener tracking
  - Foreshadowing detection
  - Promise resolution and payoff tracking
  - Unresolved promise detection

Implementation: Phase 10
"""

import re
from typing import Dict, List, Optional, Set
from datetime import datetime

from src.memory.base_memory import BaseMemory
from src.models.state import (
    ChapterData,
    StateChange,
    StateChangeType,
    NarrativeElementType,
)
from src.utils import stable_hash
class PromiseMemory(BaseMemory):
    """Manages promise and foreshadowing tracking with full history."""

    # Promise indicators (Phase 10)
    PROMISE_INDICATORS = [
        "i promise", "i swear", "i vow", "i guarantee", "i assure you",
        "promise me", "swear to me", "you have my word", "i give you my word",
        "i will", "i shall", "i won't", "i shall not",
        "i'll never", "i'll always", "i promise to",
    ]

    # Foreshadowing indicators (Phase 10)
    FORESHADOWING_INDICATORS = [
        "little did", "unknown to", "without knowing", "had no idea",
        "would soon", "was about to", "soon would", "little did know",
        "fate had", "destiny would", "unbeknownst",
    ]

    # Resolution indicators (Phase 10)
    RESOLUTION_INDICATORS = [
        "finally", "at last", "after all", "in the end", "resolved",
        "fulfilled", "completed", "finished", "concluded", "kept promise",
        "promise kept", "vow fulfilled", "came true",
    ]

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update promise state from chapter evidence (Phase 10).

        Detects promises, foreshadowing, and resolutions from the chapter text.

        Returns:
            List of StateChange objects describing promise changes.
        """
        changes: List[StateChange] = []

        # Extract promises
        promise_changes = self._extract_promises(chapter_data, chapter_num)
        changes.extend(promise_changes)

        # Extract foreshadowing
        foreshadow_changes = self._extract_foreshadowing(chapter_data, chapter_num)
        changes.extend(foreshadow_changes)

        # Check for resolutions
        resolution_changes = self._check_resolutions(chapter_data, chapter_num)
        changes.extend(resolution_changes)

        return changes

    def _extract_promises(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Extract promises from dialogue and narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            for indicator in self.PROMISE_INDICATORS:
                if indicator in sentence_lower:
                    # Extract the promise text
                    promise_text = sentence.strip()

                    # Try to identify speaker from dialogue
                    speaker = self._identify_speaker(sentence, chapter_data)

                    # Generate a unique promise ID
                    promise_id = f"promise_{stable_hash(promise_text)}"

                    # Check if this promise already exists
                    existing_promise = self.get_entry(promise_id, "promise_text")

                    if not existing_promise or not existing_promise.current:
                        # New promise
                        self.update_entry(
                            promise_id,
                            "promise_text",
                            promise_text,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.7,
                            reasoning=f"Promise extracted from text containing '{indicator}'.",
                            importance=0.9,
                        )
                        self.update_entry(
                            promise_id,
                            "speaker",
                            speaker,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.6,
                            reasoning="Speaker identified from context.",
                            importance=0.7,
                        )
                        self.update_entry(
                            promise_id,
                            "status",
                            "unresolved",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.9,
                            reasoning="New promise marked as unresolved.",
                            importance=0.9,
                        )
                        self.update_entry(
                            promise_id,
                            "chapter_made",
                            chapter_num,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=1.0,
                            reasoning="Chapter where promise was made.",
                            importance=0.8,
                        )

                        changes.append(
                            StateChange(
                                change_type=StateChangeType.INTRODUCTION,
                                target_type=NarrativeElementType.PROMISE,
                                target_id=promise_id,
                                field_key="promise_text",
                                new_value=promise_text,
                                confidence=0.7,
                                reasoning=f"New promise detected in chapter.",
                            )
                        )
                    else:
                        # Existing promise - confirm it's still unresolved
                        status_entry = self.get_entry(promise_id, "status")
                        if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.CONFIRMATION,
                                    target_type=NarrativeElementType.PROMISE,
                                    target_id=promise_id,
                                    field_key="status",
                                    old_value="unresolved",
                                    new_value="unresolved",
                                    confidence=0.6,
                                    reasoning=f"Promise remains unresolved.",
                                )
                            )

                    break  # Only count each sentence once

        return changes

    def _extract_foreshadowing(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Extract foreshadowing from narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            for indicator in self.FORESHADOWING_INDICATORS:
                if indicator in sentence_lower:
                    # Extract the foreshadowing text
                    foreshadow_text = sentence.strip()

                    # Generate a unique foreshadowing ID
                    foreshadow_id = f"foreshadow_{stable_hash(foreshadow_text)}"

                    # Check if this foreshadowing already exists
                    existing_foreshadow = self.get_entry(foreshadow_id, "foreshadow_text")

                    if not existing_foreshadow or not existing_foreshadow.current:
                        # New foreshadowing
                        self.update_entry(
                            foreshadow_id,
                            "foreshadow_text",
                            foreshadow_text,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.6,
                            reasoning=f"Foreshadowing extracted from text containing '{indicator}'.",
                            importance=0.8,
                        )
                        self.update_entry(
                            foreshadow_id,
                            "status",
                            "unresolved",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.8,
                            reasoning="New foreshadowing marked as unresolved.",
                            importance=0.8,
                        )
                        self.update_entry(
                            foreshadow_id,
                            "chapter_introduced",
                            chapter_num,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=1.0,
                            reasoning="Chapter where foreshadowing was introduced.",
                            importance=0.7,
                        )

                        changes.append(
                            StateChange(
                                change_type=StateChangeType.INTRODUCTION,
                                target_type=NarrativeElementType.PROMISE,
                                target_id=foreshadow_id,
                                field_key="foreshadow_text",
                                new_value=foreshadow_text,
                                confidence=0.6,
                                reasoning=f"New foreshadowing detected in chapter.",
                            )
                        )

                    break  # Only count each sentence once

        return changes

    def _check_resolutions(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Check if any existing promises or foreshadowing are resolved."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        # Check all unresolved promises
        for entry_id in self._entries.keys():
            if entry_id.startswith("promise_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    # Check for resolution indicators
                    for indicator in self.RESOLUTION_INDICATORS:
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
                                reasoning="Chapter where promise was resolved.",
                                importance=0.9,
                            )

                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.RESOLUTION,
                                    target_type=NarrativeElementType.PROMISE,
                                    target_id=entry_id,
                                    field_key="status",
                                    old_value=old_status,
                                    new_value="resolved",
                                    confidence=0.7,
                                    reasoning=f"Promise resolved in chapter.",
                                )
                            )
                            break

            # Check foreshadowing resolutions
            if entry_id.startswith("foreshadow_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    # Check for resolution indicators
                    for indicator in self.RESOLUTION_INDICATORS:
                        if indicator in text:
                            # Mark as resolved
                            old_status = status_entry.current.value
                            self.update_entry(
                                entry_id,
                                "status",
                                "resolved",
                                chapter=chapter_num,
                                evidence_ids=[],
                                confidence=0.6,
                                reasoning=f"Resolution detected via '{indicator}' in chapter.",
                                importance=0.8,
                            )
                            self.update_entry(
                                entry_id,
                                "chapter_resolved",
                                chapter_num,
                                chapter=chapter_num,
                                evidence_ids=[],
                                confidence=0.8,
                                reasoning="Chapter where foreshadowing was resolved.",
                                importance=0.8,
                            )

                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.RESOLUTION,
                                    target_type=NarrativeElementType.PROMISE,
                                    target_id=entry_id,
                                    field_key="status",
                                    old_value=old_status,
                                    new_value="resolved",
                                    confidence=0.6,
                                    reasoning=f"Foreshadowing resolved in chapter.",
                                )
                            )
                            break

        return changes

    def _identify_speaker(self, sentence: str, chapter_data: ChapterData) -> str:
        """Identify the speaker of a sentence from dialogue data."""
        for dialogue in chapter_data.dialogues:
            if sentence.strip() in dialogue.text:
                return dialogue.speaker or "unknown"
        return "unknown"

    def get_unresolved_promises(self) -> List[Dict]:
        """Get all unresolved promises."""
        unresolved = []
        for entry_id in self._entries.keys():
            if entry_id.startswith("promise_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    text_entry = self.get_entry(entry_id, "promise_text")
                    speaker_entry = self.get_entry(entry_id, "speaker")
                    chapter_entry = self.get_entry(entry_id, "chapter_made")

                    unresolved.append({
                        "id": entry_id,
                        "text": text_entry.current.value if text_entry and text_entry.current else "",
                        "speaker": speaker_entry.current.value if speaker_entry and speaker_entry.current else "unknown",
                        "chapter_made": chapter_entry.current.value if chapter_entry and chapter_entry.current else 0,
                    })
        return unresolved

    def get_unresolved_foreshadowing(self) -> List[Dict]:
        """Get all unresolved foreshadowing."""
        unresolved = []
        for entry_id in self._entries.keys():
            if entry_id.startswith("foreshadow_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    text_entry = self.get_entry(entry_id, "foreshadow_text")
                    chapter_entry = self.get_entry(entry_id, "chapter_introduced")

                    unresolved.append({
                        "id": entry_id,
                        "text": text_entry.current.value if text_entry and text_entry.current else "",
                        "chapter_introduced": chapter_entry.current.value if chapter_entry and chapter_entry.current else 0,
                    })
        return unresolved
