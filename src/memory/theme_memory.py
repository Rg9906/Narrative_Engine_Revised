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

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update theme state from chapter evidence (Phase 10).

        Detects themes and symbols from the chapter text and tracks their
        frequency and evolution across chapters.

        Returns:
            List of StateChange objects describing theme changes.
        """
        changes: List[StateChange] = []

        # Detect themes
        theme_changes = self._detect_themes(chapter_data, chapter_num)
        changes.extend(theme_changes)

        # Detect symbols
        symbol_changes = self._detect_symbols(chapter_data, chapter_num)
        changes.extend(symbol_changes)

        return changes

    def _detect_themes(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Detect and track themes in the chapter."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        for theme_name, keywords in self.THEME_KEYWORDS.items():
            # Count keyword occurrences
            keyword_count = sum(1 for keyword in keywords if keyword in text)

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

    def _detect_symbols(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """Detect and track symbols in the chapter."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        for symbol_name, keywords in self.SYMBOL_KEYWORDS.items():
            # Count keyword occurrences
            keyword_count = sum(1 for keyword in keywords if keyword in text)

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
