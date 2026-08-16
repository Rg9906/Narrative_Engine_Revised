"""
Theme Memory — Tracking themes, motifs, and symbols.

Tracks recurring themes, motifs, and symbols across chapters:
  - Theme detection and frequency tracking
  - Symbol identification and evolution
  - Theme payoff and resolution tracking

Implementation: Phase 10
"""

import re
from typing import Dict, List, Optional, Set
from collections import Counter

from src.memory.base_memory import BaseMemory
from src.models.state import (
    ChapterData,
    StateChange,
    StateChangeType,
    NarrativeElementType,
)
from src.utils.zero_shot_classifier import get_classifier


class ThemeMemory(BaseMemory):
    """Manages evolving theme and symbol tracking with full history."""

    # Common literary themes and their keywords (Phase 10)
    THEME_KEYWORDS = {
        "love": ["love", "romance", "passion", "heart", "devotion", "affection", "desire"],
        "death": ["death", "die", "dying", "grave", "funeral", "mortality", "corpse", "kill"],
        "power": ["power", "control", "authority", "dominance", "rule", "command", "influence"],
        "freedom": ["freedom", "liberty", "escape", "liberate", "free", "chains", "prison"],
        "betrayal": ["betray", "betrayal", "treason", "deceive", "backstab", "traitor", "lie"],
        "redemption": ["redemption", "redeem", "forgive", "forgiveness", "atone", "salvation"],
        "good_vs_evil": ["good", "evil", "right", "wrong", "moral", "virtue", "sin", "righteous"],
        "coming_of_age": ["grow", "mature", "adult", "childhood", "innocence", "experience", "youth"],
        "identity": ["identity", "self", "who am i", "belonging", "purpose", "meaning", "exist"],
        "nature_vs_civilization": ["nature", "wild", "civilization", "society", "wilderness", "urban", "natural"],
        "fate_vs_free_will": ["fate", "destiny", "choice", "free will", "destined", "chosen", "fortune"],
        "sacrifice": ["sacrifice", "give up", "surrender", "offer", "martyr", "selfless", "devote"],
        "hope": ["hope", "hopeful", "optimism", "dream", "wish", "aspire", "believe"],
        "justice": ["justice", "fairness", "law", "judgment", "righteous", "equity", "truth"],
        "isolation": ["alone", "lonely", "isolated", "solitude", "separation", "detached", "alienated"],
    }

    # Symbol keywords (Phase 10)
    SYMBOL_KEYWORDS = {
        "light": ["light", "sun", "brightness", "glow", "shine", "illuminate", "ray"],
        "darkness": ["dark", "darkness", "shadow", "night", "black", "gloom", "dim"],
        "water": ["water", "ocean", "sea", "river", "lake", "rain", "wave", "stream"],
        "fire": ["fire", "flame", "burn", "blaze", "heat", "spark", "inferno", "ash"],
        "blood": ["blood", "bleed", "wound", "cut", "injury", "vein", "crimson"],
        "mirror": ["mirror", "reflection", "glass", "image", "reflect", "duplicate"],
        "door": ["door", "gate", "entrance", "exit", "portal", "threshold", "opening"],
        "key": ["key", "lock", "unlock", "open", "secure", "access", "mechanism"],
        "tree": ["tree", "forest", "branch", "root", "leaf", "trunk", "wood"],
        "bird": ["bird", "fly", "wing", "feather", "sky", "flight", "nest"],
    }

    # A single incidental keyword hit (one use of "self" or "exist" out of 15 theme
    # categories, or "hand"/"key" out of 10 symbol categories) used to be enough to
    # permanently register a theme/symbol — meaning nearly every category fired within
    # a few chapters regardless of what the story was actually about (25 "themes"
    # detected out of 3 real chapters). Requiring a stronger per-chapter signal before
    # a brand-new theme/symbol is introduced cuts that noise; once established, any
    # further mention still counts as reinforcement (see the `old_count == 0` gate below).
    MIN_MENTIONS_TO_INTRODUCE = 2

    # A sentence "hits" a theme/symbol category when the zero-shot classifier's
    # confidence for that label meets this bar. Used only when the classifier
    # (src/utils/zero_shot_classifier.py) is actually available; otherwise
    # detection falls back unchanged to the keyword scan below.
    ZERO_SHOT_THEME_THRESHOLD = 0.6

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    @staticmethod
    def _label_by_name(category_keywords: Dict[str, List[str]]) -> Dict[str, str]:
        return {name: name.replace("_", " ") for name in category_keywords}

    def _classify_sentences(self, sentences: List[str]) -> Optional[List[Dict[str, float]]]:
        """One batched classifier call per chapter, covering BOTH theme and
        symbol labels together, shared by _detect_themes/_detect_symbols via
        update_from_chapter. (Previously each made its own separate
        classify_batch call over the identical sentence list -- doubling
        ~1.6GB BART-MNLI inference cost per chapter for no benefit.) Returns
        None (never raises) if the classifier is unavailable or the call
        fails, so callers can fall back to keyword counting cleanly."""
        classifier = get_classifier()
        if not sentences or not classifier.available:
            return None

        all_labels = list(self._label_by_name(self.THEME_KEYWORDS).values()) + \
            list(self._label_by_name(self.SYMBOL_KEYWORDS).values())
        return classifier.classify_batch(sentences, all_labels)

    def _aggregate_hit_counts(
        self, semantic_scores: Optional[List[Dict[str, float]]], category_keywords: Dict[str, List[str]]
    ) -> Optional[Dict[str, int]]:
        """Count, per category, how many sentences scored above threshold in
        the shared classify_batch results computed by _classify_sentences.
        Returns None when no classifier scores are available (caller falls
        back to keyword counting)."""
        if semantic_scores is None:
            return None

        name_by_label = {v: k for k, v in self._label_by_name(category_keywords).items()}
        counts = {name: 0 for name in category_keywords}
        for sentence_scores in semantic_scores:
            for label, score in sentence_scores.items():
                if score >= self.ZERO_SHOT_THEME_THRESHOLD:
                    name = name_by_label.get(label)
                    if name:
                        counts[name] += 1
        return counts

    @staticmethod
    def _count_hits_via_keywords(text_lower: str, category_keywords: Dict[str, List[str]]) -> Dict[str, int]:
        return {
            name: sum(1 for keyword in keywords if keyword in text_lower)
            for name, keywords in category_keywords.items()
        }

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update theme state from chapter evidence (Phase 10).

        Detects themes and symbols from the chapter text and tracks their
        frequency and evolution across chapters.

        Returns:
            List of StateChange objects describing theme changes.
        """
        changes: List[StateChange] = []

        semantic_scores = self._classify_sentences(chapter_data.sentences)

        # Detect themes
        theme_changes = self._detect_themes(chapter_data, chapter_num, semantic_scores)
        changes.extend(theme_changes)

        # Detect symbols
        symbol_changes = self._detect_symbols(chapter_data, chapter_num, semantic_scores)
        changes.extend(symbol_changes)

        return changes

    def _detect_themes(
        self, chapter_data: ChapterData, chapter_num: int,
        semantic_scores: Optional[List[Dict[str, float]]] = None,
    ) -> List[StateChange]:
        """Detect and track themes in the chapter."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        hit_counts = self._aggregate_hit_counts(semantic_scores, self.THEME_KEYWORDS)
        if hit_counts is None:
            hit_counts = self._count_hits_via_keywords(text, self.THEME_KEYWORDS)

        for theme_name, keyword_count in hit_counts.items():
            if keyword_count > 0:
                # Get existing theme entry
                theme_id = f"theme_{theme_name}"
                existing_theme = self.get_entry(theme_id, "mention_count")
                old_count = existing_theme.current.value if existing_theme and existing_theme.current else 0

                if old_count == 0 and keyword_count < self.MIN_MENTIONS_TO_INTRODUCE:
                    continue

                new_count = old_count + keyword_count

                # Update mention count
                self.update_entry(
                    theme_id,
                    "mention_count",
                    new_count,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.7,
                    reasoning=f"Theme '{theme_name}' mentioned {keyword_count} times in chapter.",
                    importance=0.8,
                )

                # Track chapters where theme appears
                chapters_entry = self.get_entry(theme_id, "chapters_present")
                old_chapters = chapters_entry.current.value if chapters_entry and chapters_entry.current else []
                chapters_present = old_chapters if chapter_num in old_chapters else old_chapters + [chapter_num]
                if chapter_num not in old_chapters:
                    self.update_entry(
                        theme_id,
                        "chapters_present",
                        chapters_present,
                        chapter=chapter_num,
                        evidence_ids=[],
                        confidence=0.9,
                        reasoning=f"Theme '{theme_name}' appears in new chapter.",
                        importance=0.7,
                    )

                # ContextRetriever's <CoreThemes> tier reads a "description" field —
                # without this, every deterministically-detected theme rendered as an
                # empty `<Theme id="theme_x"></Theme>` tag in every LLM prompt (only
                # LLM-authored themes ever populated "description"), conveying zero
                # information despite taking up context budget.
                description = (
                    f"Recurring theme of '{theme_name}' — mentioned {new_count} time(s) "
                    f"across chapter(s) {', '.join(str(c) for c in chapters_present)}."
                )
                self.update_entry(
                    theme_id,
                    "description",
                    description,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.7,
                    reasoning="Auto-generated summary of keyword-detected theme frequency.",
                    importance=0.6,
                )

                # Check for theme introduction or evolution
                if old_count == 0:
                    # New theme introduced
                    self.update_entry(
                        theme_id,
                        "theme_name",
                        theme_name,
                        chapter=chapter_num,
                        evidence_ids=[],
                        confidence=0.8,
                        reasoning=f"Theme '{theme_name}' introduced in chapter.",
                        importance=0.9,
                    )
                    changes.append(
                        StateChange(
                            change_type=StateChangeType.INTRODUCTION,
                            target_type=NarrativeElementType.THEME,
                            target_id=theme_id,
                            field_key="theme_name",
                            new_value=theme_name,
                            confidence=0.8,
                            reasoning=f"New theme detected in chapter.",
                        )
                    )
                else:
                    changes.append(
                        StateChange(
                            change_type=StateChangeType.EVOLUTION,
                            target_type=NarrativeElementType.THEME,
                            target_id=theme_id,
                            field_key="mention_count",
                            old_value=old_count,
                            new_value=new_count,
                            confidence=0.7,
                            reasoning=f"Theme mention count increased.",
                        )
                    )

        return changes

    def _detect_symbols(
        self, chapter_data: ChapterData, chapter_num: int,
        semantic_scores: Optional[List[Dict[str, float]]] = None,
    ) -> List[StateChange]:
        """Detect and track symbols in the chapter."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        hit_counts = self._aggregate_hit_counts(semantic_scores, self.SYMBOL_KEYWORDS)
        if hit_counts is None:
            hit_counts = self._count_hits_via_keywords(text, self.SYMBOL_KEYWORDS)

        for symbol_name, keyword_count in hit_counts.items():
            if keyword_count > 0:
                # Get existing symbol entry
                symbol_id = f"symbol_{symbol_name}"
                existing_symbol = self.get_entry(symbol_id, "mention_count")
                old_count = existing_symbol.current.value if existing_symbol and existing_symbol.current else 0

                if old_count == 0 and keyword_count < self.MIN_MENTIONS_TO_INTRODUCE:
                    continue

                new_count = old_count + keyword_count

                # Update mention count
                self.update_entry(
                    symbol_id,
                    "mention_count",
                    new_count,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.7,
                    reasoning=f"Symbol '{symbol_name}' mentioned {keyword_count} times in chapter.",
                    importance=0.7,
                )

                # Track chapters where symbol appears
                chapters_entry = self.get_entry(symbol_id, "chapters_present")
                old_chapters = chapters_entry.current.value if chapters_entry and chapters_entry.current else []
                chapters_present = old_chapters if chapter_num in old_chapters else old_chapters + [chapter_num]
                if chapter_num not in old_chapters:
                    self.update_entry(
                        symbol_id,
                        "chapters_present",
                        chapters_present,
                        chapter=chapter_num,
                        evidence_ids=[],
                        confidence=0.9,
                        reasoning=f"Symbol '{symbol_name}' appears in new chapter.",
                        importance=0.6,
                    )

                # Symbols share state.themes with themes (both keyed there by ThemeMemory),
                # so ContextRetriever's <CoreThemes> tier renders these too — same
                # "description" field gap as themes above.
                description = (
                    f"Recurring symbol of '{symbol_name}' — mentioned {new_count} time(s) "
                    f"across chapter(s) {', '.join(str(c) for c in chapters_present)}."
                )
                self.update_entry(
                    symbol_id,
                    "description",
                    description,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.7,
                    reasoning="Auto-generated summary of keyword-detected symbol frequency.",
                    importance=0.5,
                )

                # Check for symbol introduction or evolution
                if old_count == 0:
                    # New symbol introduced
                    self.update_entry(
                        symbol_id,
                        "symbol_name",
                        symbol_name,
                        chapter=chapter_num,
                        evidence_ids=[],
                        confidence=0.8,
                        reasoning=f"Symbol '{symbol_name}' introduced in chapter.",
                        importance=0.8,
                    )
                    changes.append(
                        StateChange(
                            change_type=StateChangeType.INTRODUCTION,
                            target_type=NarrativeElementType.THEME,
                            target_id=symbol_id,
                            field_key="symbol_name",
                            new_value=symbol_name,
                            confidence=0.8,
                            reasoning=f"New symbol detected in chapter.",
                        )
                    )
                else:
                    changes.append(
                        StateChange(
                            change_type=StateChangeType.EVOLUTION,
                            target_type=NarrativeElementType.THEME,
                            target_id=symbol_id,
                            field_key="mention_count",
                            old_value=old_count,
                            new_value=new_count,
                            confidence=0.7,
                            reasoning=f"Symbol mention count increased.",
                        )
                    )

        return changes

    def get_theme_summary(self) -> Dict[str, Dict]:
        """Get a summary of all tracked themes."""
        summary = {}
        for entry_id in self._entries.keys():
            if entry_id.startswith("theme_"):
                theme_state = self.get_entity_state(entry_id)
                if theme_state:
                    name_entry = theme_state.get("theme_name")
                    count_entry = theme_state.get("mention_count")
                    chapters_entry = theme_state.get("chapters_present")

                    if name_entry and name_entry.current:
                        summary[entry_id] = {
                            "name": name_entry.current.value,
                            "mention_count": count_entry.current.value if count_entry and count_entry.current else 0,
                            "chapters_present": chapters_entry.current.value if chapters_entry and chapters_entry.current else [],
                        }
        return summary

    def get_symbol_summary(self) -> Dict[str, Dict]:
        """Get a summary of all tracked symbols."""
        summary = {}
        for entry_id in self._entries.keys():
            if entry_id.startswith("symbol_"):
                symbol_state = self.get_entity_state(entry_id)
                if symbol_state:
                    name_entry = symbol_state.get("symbol_name")
                    count_entry = symbol_state.get("mention_count")
                    chapters_entry = symbol_state.get("chapters_present")

                    if name_entry and name_entry.current:
                        summary[entry_id] = {
                            "name": name_entry.current.value,
                            "mention_count": count_entry.current.value if count_entry and count_entry.current else 0,
                            "chapters_present": chapters_entry.current.value if chapters_entry and chapters_entry.current else [],
                        }
        return summary
