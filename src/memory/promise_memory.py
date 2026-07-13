"""
Promise Memory — Tracking promises, foreshadowing, and resolutions.

Tracks narrative promises and foreshadowing across chapters:
  - Promise extraction and speaker/listener tracking
  - Foreshadowing detection
  - Promise resolution and payoff tracking
  - Unresolved promise detection

Implementation: Phase 10, enriched in Enhancement Sprint
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
    StateSnapshot,
)
from src.utils import stable_hash


class PromiseMemory(BaseMemory):
    """Manages promise and foreshadowing tracking with full history and metadata."""

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

        # Check for semantic resolution markers
        semantic_changes = self._check_semantic_resolutions(chapter_data, chapter_num)
        changes.extend(semantic_changes)

        return changes

    def _extract_promises(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Extract promises from dialogue and narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            for indicator in self.PROMISE_INDICATORS:
                if indicator in sentence_lower:
                    promise_text = sentence.strip()

                    # Identify speaker and listener
                    speaker = self._identify_speaker(sentence, chapter_data)
                    speaker_id = self._normalize_entity_id(speaker) if speaker != "unknown" else "unknown"

                    # Identify listener (first other person mentioned in the sentence, otherwise in scenecast)
                    listener_id = "unknown"
                    for entity in chapter_data.entities:
                        if entity.label.lower() == "person" and entity.text.lower() != speaker.lower():
                            if entity.text.lower() in sentence_lower:
                                listener_id = self._normalize_entity_id(entity.text)
                                break
                    # Fallback to any other person in the chapter entities
                    if listener_id == "unknown":
                        for entity in chapter_data.entities:
                            if entity.label.lower() == "person" and entity.text.lower() != speaker.lower():
                                listener_id = self._normalize_entity_id(entity.text)
                                break

                    # Generate a unique promise ID
                    promise_id = f"promise_{stable_hash(promise_text)}"

                    # Check if this promise already exists
                    existing_promise = self.get_entry(promise_id, "promise_text")

                    if not existing_promise or not existing_promise.current:
                        # New promise (using new status OPEN, speaker_id, listener_id, climax_proximity_threshold)
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
                            "speaker_id",
                            speaker_id,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.6,
                            reasoning="Speaker identified from dialogue context.",
                            importance=0.7,
                        )
                        self.update_entry(
                            promise_id,
                            "listener_id",
                            listener_id,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.5,
                            reasoning="Listener identified from neighboring entities.",
                            importance=0.6,
                        )
                        self.update_entry(
                            promise_id,
                            "status",
                            "OPEN",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.9,
                            reasoning="New promise marked as OPEN.",
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
                        self.update_entry(
                            promise_id,
                            "climax_proximity_threshold",
                            3,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.5,
                            reasoning="Default climax proximity threshold.",
                            importance=0.5,
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
                        # Existing promise - confirm it's still OPEN
                        status_entry = self.get_entry(promise_id, "status")
                        if status_entry and status_entry.current and status_entry.current.value in ("unresolved", "OPEN"):
                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.CONFIRMATION,
                                    target_type=NarrativeElementType.PROMISE,
                                    target_id=promise_id,
                                    field_key="status",
                                    old_value=status_entry.current.value,
                                    new_value=status_entry.current.value,
                                    confidence=0.6,
                                    reasoning=f"Promise remains open.",
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
                    foreshadow_text = sentence.strip()
                    foreshadow_id = f"foreshadow_{stable_hash(foreshadow_text)}"
                    existing_foreshadow = self.get_entry(foreshadow_id, "foreshadow_text")

                    if not existing_foreshadow or not existing_foreshadow.current:
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
                            "OPEN",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.8,
                            reasoning="New foreshadowing marked as OPEN.",
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

                    break

        return changes

    def _check_resolutions(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Check if any existing promises or foreshadowing are resolved via explicit keywords."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        # Check all unresolved/OPEN promises
        for entry_id in self._entries.keys():
            if entry_id.startswith("promise_"):
                # Ignore promises made in the current chapter
                chapter_made_entry = self.get_entry(entry_id, "chapter_made")
                if chapter_made_entry and chapter_made_entry.current and chapter_made_entry.current.value >= chapter_num:
                    continue

                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value in ("unresolved", "OPEN"):
                    for indicator in self.RESOLUTION_INDICATORS:
                        if indicator in text:
                            old_status = status_entry.current.value
                            self.update_entry(
                                entry_id,
                                "status",
                                "FULFILLED",
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
                                    new_value="FULFILLED",
                                    confidence=0.7,
                                    reasoning=f"Promise resolved in chapter.",
                                )
                            )
                            break

            # Check foreshadowing resolutions
            if entry_id.startswith("foreshadow_"):
                # Ignore foreshadowing introduced in the current chapter
                chapter_intro_entry = self.get_entry(entry_id, "chapter_introduced")
                if chapter_intro_entry and chapter_intro_entry.current and chapter_intro_entry.current.value >= chapter_num:
                    continue

                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value in ("unresolved", "OPEN"):
                    for indicator in self.RESOLUTION_INDICATORS:
                        if indicator in text:
                            old_status = status_entry.current.value
                            self.update_entry(
                                entry_id,
                                "status",
                                "FULFILLED",
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
                                    new_value="FULFILLED",
                                    confidence=0.6,
                                    reasoning=f"Foreshadowing resolved in chapter.",
                                )
                            )
                            break

        return changes

    def _check_semantic_resolutions(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Perform tokenized keyword-overlap and semantic checks to match unresolved threads."""
        changes: List[StateChange] = []
        stopwords = {
            "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", 
            "he", "him", "his", "she", "her", "hers", "it", "its", "they", "them", "their", 
            "what", "which", "who", "whom", "this", "that", "am", "is", "are", "was", "were", 
            "be", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", 
            "a", "an", "the", "and", "but", "if", "or", "because", "as", "until", "while", 
            "of", "at", "by", "for", "with", "about", "against", "between", "into", "through", 
            "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", 
            "out", "on", "off", "over", "under", "again", "further", "then", "once", "promise", 
            "swear", "vow"
        }

        for entry_id in self._entries.keys():
            if entry_id.startswith("promise_"):
                # Ignore promises made in the current chapter
                chapter_made_entry = self.get_entry(entry_id, "chapter_made")
                if chapter_made_entry and chapter_made_entry.current and chapter_made_entry.current.value >= chapter_num:
                    continue

                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value in ("unresolved", "OPEN"):
                    promise_text_entry = self.get_entry(entry_id, "promise_text")
                    if not promise_text_entry or not promise_text_entry.current:
                        continue
                    promise_text = promise_text_entry.current.value

                    # Tokenize and extract key content words
                    promise_words = [w.strip(".,!?\"'") for w in promise_text.lower().split()]
                    promise_keywords = {w for w in promise_words if w and w not in stopwords and len(w) > 2}

                    resolved = False
                    reasoning = ""

                    # 1. Search for keyword overlap in sentences
                    for sentence in chapter_data.sentences:
                        sent_words = {w.strip(".,!?\"'").lower() for w in sentence.split()}
                        overlap = promise_keywords.intersection(sent_words)

                        # High overlap threshold
                        if len(overlap) >= max(1, int(len(promise_keywords) * 0.4)):
                            resolution_words = {"kept", "fulfill", "done", "accomplished", "return", "back", "succeed", "happen", "did", "vow", "word"}
                            if sent_words.intersection(resolution_words) or sent_words.intersection(self.RESOLUTION_INDICATORS):
                                resolved = True
                                reasoning = f"Semantic overlap found in sentence: '{sentence}' containing keywords {overlap}."
                                break

                    # 2. Search dialogue text
                    if not resolved:
                        for dialogue in chapter_data.dialogues:
                            dialogue_words = {w.strip(".,!?\"'").lower() for w in dialogue.text.split()}
                            overlap = promise_keywords.intersection(dialogue_words)
                            if len(overlap) >= max(1, int(len(promise_keywords) * 0.4)):
                                resolved = True
                                reasoning = f"Dialogue from '{dialogue.speaker}' semantically matches promise: '{dialogue.text}'."
                                break

                    if resolved:
                        old_status = status_entry.current.value
                        self.update_entry(
                            entry_id,
                            "status",
                            "FULFILLED",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.8,
                            reasoning=reasoning,
                            importance=0.9,
                        )
                        self.update_entry(
                            entry_id,
                            "chapter_resolved",
                            chapter_num,
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.8,
                            reasoning="Marked FULFILLED via semantic resolution.",
                            importance=0.9,
                        )
                        changes.append(
                            StateChange(
                                change_type=StateChangeType.RESOLUTION,
                                target_type=NarrativeElementType.PROMISE,
                                target_id=entry_id,
                                field_key="status",
                                old_value=old_status,
                                new_value="FULFILLED",
                                confidence=0.8,
                                reasoning=reasoning,
                            )
                        )
        return changes

    def _identify_speaker(self, sentence: str, chapter_data: ChapterData) -> str:
        """Identify the speaker of a sentence from dialogue data."""
        for dialogue in chapter_data.dialogues:
            if sentence.strip() in dialogue.text:
                return dialogue.speaker or "unknown"
        return "unknown"

    def _normalize_entity_id(self, text: str) -> str:
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return text.strip("_")

    def get_unresolved_promises(self) -> List[Dict]:
        """Get all unresolved/OPEN promises with complete fields."""
        unresolved = []
        for entry_id in self._entries.keys():
            if entry_id.startswith("promise_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value in ("unresolved", "OPEN"):
                    text_entry = self.get_entry(entry_id, "promise_text")
                    speaker_entry = self.get_entry(entry_id, "speaker_id") or self.get_entry(entry_id, "speaker")
                    listener_entry = self.get_entry(entry_id, "listener_id")
                    chapter_entry = self.get_entry(entry_id, "chapter_made")
                    climax_entry = self.get_entry(entry_id, "climax_proximity_threshold")

                    unresolved.append({
                        "id": entry_id,
                        "text": text_entry.current.value if text_entry and text_entry.current else "",
                        "speaker": speaker_entry.current.value if speaker_entry and speaker_entry.current else "unknown",
                        "speaker_id": speaker_entry.current.value if speaker_entry and speaker_entry.current else "unknown",
                        "listener_id": listener_entry.current.value if listener_entry and listener_entry.current else "unknown",
                        "chapter_made": chapter_entry.current.value if chapter_entry and chapter_entry.current else 0,
                        "climax_proximity_threshold": climax_entry.current.value if climax_entry and climax_entry.current else 3,
                        "status": status_entry.current.value,
                    })
        return unresolved

    def get_unresolved_foreshadowing(self) -> List[Dict]:
        """Get all unresolved foreshadowing."""
        unresolved = []
        for entry_id in self._entries.keys():
            if entry_id.startswith("foreshadow_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value in ("unresolved", "OPEN"):
                    text_entry = self.get_entry(entry_id, "foreshadow_text")
                    chapter_entry = self.get_entry(entry_id, "chapter_introduced")

                    unresolved.append({
                        "id": entry_id,
                        "text": text_entry.current.value if text_entry and text_entry.current else "",
                        "chapter_introduced": chapter_entry.current.value if chapter_entry and chapter_entry.current else 0,
                        "status": status_entry.current.value,
                    })
        return unresolved
