"""
Spatiotemporal Inspector — Generalized alibi/consistency checking.

Replaces a prior version of this capability that was hardcoded to one demo
manuscript's character names ("Laurie", "Talia", "Sebastian") and a specific
chapter number, and didn't actually compare anything — it unconditionally
emitted the same three findings whenever those names appeared. That version
was deleted rather than kept "working."

This version operates purely on structured state: StateEntry location
trajectories (src/models/state.py's versioned history) and current_state.timeline
(now populated for real — see Pipeline._extract_relations and the World+Timeline
LLM stage in src/pipeline/llm_extraction.py). No manuscript-specific assumptions;
it runs unchanged on any novel.

Checks, modeled on TimelineInspector's pattern of scanning structured state
generically rather than hardcoding names:
  1. Unexplained location jump — a character's recorded location changed between
     chapters with no timeline event describing how they got there.
  2. Object custody without presence — a world item's location/owner changed to
     somewhere no character is recorded as having been that chapter.
  3. Intra-chapter location conflict — the same chapter proposed two different
     locations for the same character (e.g. deterministic evidence vs. an LLM
     stage disagreeing), which never got reconciled to one value.

Implementation: Phase 5 (rebuilt from src/review/alibi_inspector.py, deleted
in Phase 1 of the deterministic-first migration).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.review.inspector import BaseInspector, Finding

_MOVEMENT_KEYWORDS = (
    "move", "moves", "moved", "travel", "walk", "walks", "walked", "arrive", "arrives",
    "arrived", "enter", "enters", "entered", "flee", "flees", "fled", "return", "returns",
    "returned", "goes", "went", "drive", "drives", "drove", "ride", "rides", "rode",
    "run", "runs", "ran", "flew", "fly", "flies", "sail", "sails", "sailed", "slips",
    "slipped", "crosses", "crossed",
)


class SpatiotemporalInspector(BaseInspector):
    """Inspects character/object location history for unexplained movement or contradictions."""

    @property
    def name(self) -> str:
        return "Spatiotemporal Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        findings.extend(self._check_unexplained_location_jumps(state, chapter))
        findings.extend(self._check_object_custody_without_presence(state, chapter))
        findings.extend(self._check_intra_chapter_location_conflict(state, delta, chapter))

        return findings

    # ------------------------------------------------------------------

    def _check_unexplained_location_jumps(self, state, chapter: int) -> List[Finding]:
        findings: List[Finding] = []

        for char_id, fields in state.characters.items():
            location_entry = fields.get("location")
            if not location_entry:
                continue
            trajectory = location_entry.get_trajectory()
            names = self._name_variants(char_id, fields)

            for prev_snap, curr_snap in zip(trajectory, trajectory[1:]):
                if prev_snap.value is None or curr_snap.value is None:
                    continue
                if prev_snap.value == curr_snap.value or prev_snap.chapter == curr_snap.chapter:
                    continue

                if self._has_movement_event(state, names, prev_snap.chapter, curr_snap.chapter):
                    continue

                findings.append(Finding(
                    severity="note",
                    category="consistency",
                    title="Unexplained location change",
                    description=(
                        f"Character '{char_id}' moved from '{prev_snap.value}' (chapter {prev_snap.chapter}) "
                        f"to '{curr_snap.value}' (chapter {curr_snap.chapter}) with no timeline event "
                        f"describing the transition."
                    ),
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[char_id],
                    confidence=0.5,
                ))

        return findings

    def _check_object_custody_without_presence(self, state, chapter: int) -> List[Finding]:
        findings: List[Finding] = []

        # Pre-compute each character's location per chapter for fast lookup.
        char_location_by_chapter: Dict[str, Dict[int, str]] = {}
        for char_id, fields in state.characters.items():
            location_entry = fields.get("location")
            if not location_entry:
                continue
            per_chapter = {}
            for snap in location_entry.get_trajectory():
                if snap.value is not None:
                    per_chapter[snap.chapter] = str(snap.value).strip().lower()
            char_location_by_chapter[char_id] = per_chapter

        for item_id, fields in state.world.items():
            location_entry = fields.get("location")
            if not location_entry or not location_entry.current or location_entry.current.value is None:
                continue
            item_chapter = location_entry.current.chapter
            item_location = str(location_entry.current.value).strip().lower()
            if not item_location:
                continue

            anyone_present = False
            for char_id, per_chapter in char_location_by_chapter.items():
                # Nearest known location at or before this chapter.
                known_chapters = [c for c in per_chapter if c <= item_chapter]
                if not known_chapters:
                    continue
                nearest = max(known_chapters)
                char_loc = per_chapter[nearest]
                if char_loc and (char_loc in item_location or item_location in char_loc):
                    anyone_present = True
                    break

            if not anyone_present and char_location_by_chapter:
                findings.append(Finding(
                    severity="warning",
                    category="consistency",
                    title="Object relocated with no one present",
                    description=(
                        f"World item '{item_id}' is recorded at location '{location_entry.current.value}' "
                        f"as of chapter {item_chapter}, but no character's known location for that chapter "
                        f"matches — no one is recorded as having been there to move or use it."
                    ),
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[item_id],
                    confidence=0.5,
                ))

        return findings

    def _check_intra_chapter_location_conflict(self, state, delta, chapter: int) -> List[Finding]:
        findings: List[Finding] = []
        if not delta or not getattr(delta, "changes", None):
            return findings

        from src.models.state import NarrativeElementType

        proposed_by_char: Dict[str, set] = {}
        for change in delta.changes:
            if change.target_type == NarrativeElementType.CHARACTER and change.field_key == "location":
                if change.new_value is None:
                    continue
                proposed_by_char.setdefault(change.target_id, set()).add(str(change.new_value).strip().lower())

        for char_id, values in proposed_by_char.items():
            if len(values) > 1:
                findings.append(Finding(
                    severity="warning",
                    category="consistency",
                    title="Conflicting location proposals in the same chapter",
                    description=(
                        f"Character '{char_id}' was placed in multiple different locations within the "
                        f"same chapter's updates: {sorted(values)}. These were never reconciled to one value."
                    ),
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[char_id],
                    confidence=0.6,
                ))

        return findings

    # ------------------------------------------------------------------

    def _name_variants(self, char_id: str, fields: dict) -> List[str]:
        names = [char_id.lower()]
        canonical_entry = fields.get("canonical_name")
        if canonical_entry and canonical_entry.current and canonical_entry.current.value:
            names.append(str(canonical_entry.current.value).strip().lower())
        aliases_entry = fields.get("aliases")
        if aliases_entry and aliases_entry.current and isinstance(aliases_entry.current.value, list):
            names.extend(str(a).strip().lower() for a in aliases_entry.current.value if a)
        return [n for n in names if n]

    def _has_movement_event(self, state, names: List[str], from_chapter: int, to_chapter: int) -> bool:
        for event in getattr(state, "timeline", []):
            evt_chapter = event.get("chapter")
            if evt_chapter is None or not (from_chapter < evt_chapter <= to_chapter):
                continue
            subject = str(event.get("subject") or "").strip().lower()
            if not any(subject == n or subject in n or n in subject for n in names):
                continue
            predicate = str(event.get("predicate") or "").lower()
            if any(kw in predicate for kw in _MOVEMENT_KEYWORDS):
                return True
        return False
