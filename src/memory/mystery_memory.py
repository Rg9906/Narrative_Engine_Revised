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
from src.utils import stable_hash
from src.utils.zero_shot_classifier import get_classifier


class MysteryMemory(BaseMemory):
    """Manages mystery and question tracking with full history."""

    # Bare wh-words are only a mystery signal when the sentence is an actual question —
    # "how" and "why" show up constantly in ordinary narration ("she wondered how to
    # begin", "that's why he left") and firing on those alone drowned every real
    # mystery in noise (56 "mysteries" out of 3 chapters in early testing). Gated by
    # _is_question() below rather than dropped, since real unresolved questions
    # ("Who killed him?") are exactly what this tracker exists to catch.
    QUESTION_STARTERS = ("who", "what", "where", "when", "why", "how")

    # Strong, unambiguous mystery language — safe to trigger regardless of punctuation,
    # since these phrases essentially never appear as incidental narration. Previously also
    # included "hidden", "unknown", "strange", "confused", "don't know", "couldn't
    # understand" — all common in ordinary literary description/dialogue ("that's what makes
    # it strange", "I don't know") with no connection to an actual mystery-genre plot device,
    # so they fired on normal prose rather than real mysteries.
    MYSTERY_INDICATORS = [
        "mystery", "secret", "puzzle", "riddle", "enigma",
        "baffled", "no one knows", "nobody knows", "remains a mystery",
    ]

    # Clue indicators — narrowed to phrases that actually signal evidence being
    # surfaced. The previous list included ordinary perception/cognition verbs (saw,
    # found, realized, understood, noticed, observed) that fire on nearly every
    # paragraph of prose, making "clue" detection meaningless noise rather than signal.
    # First pass only kept multi-word compounds ("piece of evidence"), which turned out
    # too narrow to catch how clues are actually phrased in prose ("footprint by the
    # door", "the evidence was clear") — reintroduces bare genre-specific nouns that are
    # still rare enough in ordinary narration not to reopen the original noise problem.
    CLUE_INDICATORS = [
        "clue", "evidence", "telltale", "incriminating", "fingerprint",
        "footprint", "forensic", "alibi", "murder weapon",
        "uncovered a", "discovered a", "hint of", "gave it away",
    ]

    # Revelation/resolution indicators. Previously also included "it was", "realized
    # that", "understood", "answer", "explanation", "solution" — everyday phrases that
    # appear in almost any chapter regardless of whether a mystery was actually resolved.
    # Combined with the old whole-chapter-text scan below, that meant nearly any chapter
    # would blanket-resolve every currently open mystery. Narrowed to language that's
    # specifically about a truth being uncovered.
    REVELATION_INDICATORS = [
        "revealed", "secret revealed", "discovered the truth",
        "finally understood the truth", "the truth was",
        "uncovered the truth", "exposed", "came to light", "became clear",
        "solved the", "confessed",
    ]

    # Ordinary English words dropped from relevance-overlap matching below — without this,
    # nearly every mystery/revelation sentence pair would "overlap" on words like "the" or
    # "was" and the specificity check would be meaningless.
    _STOPWORDS = {
        "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "by", "for",
        "with", "was", "were", "is", "are", "be", "been", "he", "she", "it", "they",
        "his", "her", "its", "their", "that", "this", "had", "have", "has", "not",
    }

    # Semantic (zero-shot) labels used as an *additional* signal alongside the
    # explicit keyword/question checks above — never a replacement. Deliberately
    # stricter than ThemeMemory's threshold (0.6) given the mystery/clue noise
    # problem fixed on 2026-07-28 (56 false "mysteries" out of 3 chapters);
    # only used when src/utils/zero_shot_classifier.py reports itself available.
    ZERO_SHOT_MYSTERY_LABELS = {
        "mystery": "poses an unresolved mystery or question",
        "clue": "reveals a clue or piece of evidence",
        "revelation": "resolves or reveals a secret",
    }
    ZERO_SHOT_MYSTERY_THRESHOLD = 0.75

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def _classify_sentences(self, sentences: List[str]) -> Optional[Dict[str, Dict[str, float]]]:
        """One batched classifier call per chapter, shared across mystery/clue/
        revelation detection. Returns {sentence: {label_key: score}}, or None
        (never raises) if the classifier is unavailable or the call fails."""
        classifier = get_classifier()
        if not sentences or not classifier.available:
            return None

        labels = list(self.ZERO_SHOT_MYSTERY_LABELS.values())
        results = classifier.classify_batch(sentences, labels)
        if results is None:
            return None

        per_sentence: Dict[str, Dict[str, float]] = {}
        for sentence, scores in zip(sentences, results):
            per_sentence[sentence] = {
                key: scores.get(label, 0.0) for key, label in self.ZERO_SHOT_MYSTERY_LABELS.items()
            }
        return per_sentence

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update mystery state from chapter evidence (Phase 10).

        Detects mysteries, clues, and revelations from the chapter text.

        Returns:
            List of StateChange objects describing mystery changes.
        """
        changes: List[StateChange] = []

        semantic_scores = self._classify_sentences(chapter_data.sentences)

        # Extract mysteries
        mystery_changes = self._extract_mysteries(chapter_data, chapter_num, semantic_scores)
        changes.extend(mystery_changes)

        # Extract clues
        clue_changes = self._extract_clues(chapter_data, chapter_num, semantic_scores)
        changes.extend(clue_changes)

        # Check for revelations
        revelation_changes = self._check_revelations(chapter_data, chapter_num, semantic_scores)
        changes.extend(revelation_changes)

        return changes

    def _is_question(self, sentence: str) -> bool:
        """A sentence counts as a real question only if it's phrased and punctuated as one."""
        stripped = sentence.strip()
        if not stripped.endswith("?"):
            return False
        first_word = re.split(r"\s+", stripped.lower(), maxsplit=1)[0].strip(".,!?\"'") if stripped else ""
        return first_word in self.QUESTION_STARTERS

    def _extract_mysteries(
        self, chapter_data: ChapterData, chapter_num: int,
        semantic_scores: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[StateChange]:
        """Extract mysteries and questions from dialogue and narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            matched_indicator = None
            for indicator in self.MYSTERY_INDICATORS:
                if indicator in sentence_lower:
                    matched_indicator = indicator
                    break
            if matched_indicator is None and self._is_question(sentence):
                matched_indicator = "unresolved question"
            if matched_indicator is None and semantic_scores:
                score = semantic_scores.get(sentence, {}).get("mystery", 0.0)
                if score >= self.ZERO_SHOT_MYSTERY_THRESHOLD:
                    matched_indicator = "semantic: unresolved mystery/question"

            if not matched_indicator:
                continue

            indicator = matched_indicator
            mystery_text = sentence.strip()

            # Generate a unique mystery ID
            mystery_id = f"mystery_{stable_hash(mystery_text)}"

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

        return changes

    def _extract_clues(
        self, chapter_data: ChapterData, chapter_num: int,
        semantic_scores: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[StateChange]:
        """Extract clues that might relate to existing mysteries."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()

            matched_indicators = list(self.CLUE_INDICATORS)
            semantic_hit = (
                semantic_scores.get(sentence, {}).get("clue", 0.0) >= self.ZERO_SHOT_MYSTERY_THRESHOLD
                if semantic_scores else False
            )
            if semantic_hit:
                matched_indicators = matched_indicators + ["semantic: reveals a clue"]

            for indicator in matched_indicators:
                is_semantic = indicator.startswith("semantic:")
                if is_semantic or indicator in sentence_lower:
                    # Extract the clue text
                    clue_text = sentence.strip()

                    # Try to associate with existing mysteries
                    # For simplicity, we'll create a general clue entry
                    clue_id = f"clue_{stable_hash(clue_text)}_{chapter_num}"

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

    def _mentions_mystery(self, sentence_lower: str, mystery_text: str) -> bool:
        """A revelation sentence only resolves a SPECIFIC mystery if it shares real content
        words with that mystery's text — otherwise any revelation-flavored sentence anywhere
        in the chapter would resolve every open mystery regardless of relevance."""
        mystery_words = {
            w for w in re.findall(r"[a-z']+", mystery_text.lower()) if w not in self._STOPWORDS and len(w) > 2
        }
        if not mystery_words:
            return False
        sentence_words = {w for w in re.findall(r"[a-z']+", sentence_lower) if w not in self._STOPWORDS}
        return len(mystery_words & sentence_words) >= 2

    def _check_revelations(
        self, chapter_data: ChapterData, chapter_num: int,
        semantic_scores: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[StateChange]:
        """Check if any existing mysteries are resolved by this chapter's text."""
        changes: List[StateChange] = []

        # Check all unresolved mysteries
        for entry_id in self._entries.keys():
            if entry_id.startswith("mystery_"):
                status_entry = self.get_entry(entry_id, "status")
                if status_entry and status_entry.current and status_entry.current.value == "unresolved":
                    text_entry = self.get_entry(entry_id, "mystery_text")
                    mystery_text = text_entry.current.value if text_entry and text_entry.current else ""

                    # Check for revelation indicators, sentence by sentence, requiring the
                    # sentence to actually be about this specific mystery. The semantic
                    # check is gated by the same _mentions_mystery specificity requirement
                    # as the keyword path — it only adds *how* a sentence is recognized as
                    # revelation-flavored, never loosens which mystery it can resolve.
                    matched_indicator = None
                    for sentence in chapter_data.sentences:
                        sentence_lower = sentence.lower()
                        for indicator in self.REVELATION_INDICATORS:
                            if indicator in sentence_lower and self._mentions_mystery(sentence_lower, mystery_text):
                                matched_indicator = indicator
                                break
                        if not matched_indicator and semantic_scores:
                            score = semantic_scores.get(sentence, {}).get("revelation", 0.0)
                            if score >= self.ZERO_SHOT_MYSTERY_THRESHOLD and self._mentions_mystery(sentence_lower, mystery_text):
                                matched_indicator = "semantic: resolves a secret"
                        if matched_indicator:
                            break

                    if matched_indicator:
                        old_status = status_entry.current.value
                        self.update_entry(
                            entry_id,
                            "status",
                            "resolved",
                            chapter=chapter_num,
                            evidence_ids=[],
                            confidence=0.7,
                            reasoning=f"Resolution detected via '{matched_indicator}' in a sentence referencing this mystery.",
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
                                reasoning="Mystery resolved in chapter.",
                            )
                        )

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
