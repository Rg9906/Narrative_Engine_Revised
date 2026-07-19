"""
Validation Engine — Gatekeeper between LLM proposals and canonical NarrativeState.

The engine owns structured knowledge; the LLM owns interpretation — but
interpretation is not automatically fact. Every LLM-authored proposal
(character/relationship/world updates from src/pipeline/llm_extraction.py)
is a hypothesis until it clears this gate:

  1. Schema/confidence floor — reject proposals below the configured minimum
     confidence (src/config/default.yaml: narrative_state.min_confidence).
  2. Evidence support — a brand-new entity (never seen before this chapter)
     should be grounded in what deterministic NLP actually found (GLiNER
     entities, FastCoref clusters, dependency-parsed relations, dialogue
     speakers), not invented from nothing. Existing entities don't need this —
     the LLM interpreting/evolving something already established (e.g. "Laurie
     feels anxious") is expected reasoning, not a hallucination risk.
  3. Consistency-checker cross-reference — Stage D of the LLM extraction engine
     (src/pipeline/llm_extraction.py) already cross-references proposals against
     each other and against existing state, emitting structural_mysteries. This
     engine treats any entity named in those mysteries as a live signal, not a
     side-channel: it lowers confidence or blocks outright depending on how
     otherwise-supported the entity is.
  4. Field-level contradiction — generalizes what used to be a
     character-only, six-field, post-hoc "revert if lower confidence" check
     (previously in NarrativeStateEngine.reconcile_state_changes) into a
     pre-write gate usable for any entity type. Fields expected to stay stable
     absent strong evidence (physical traits, alive/status, canonical name)
     are treated differently from fields expected to evolve every chapter
     (goals, emotional_state, location, inventory, arc_stage, ...).

Deterministic NLP evidence itself (StateEngine's Pass 1) is NOT gated here —
GLiNER/FastCoref/dependency parsing/dialogue extraction are the trusted
baseline the LLM is meant to be interpreting, not a source of hallucination
in the same sense an LLM completion is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Set

logger = logging.getLogger("NarrativeEngine.Engines.Validation")


# Fields where a changed value is treated as a possible contradiction worth flagging (facts
# that shouldn't casually change chapter to chapter) rather than expected narrative evolution
# (goals, emotional_state, location, inventory, arc_stage, relationship_label, ... all fall
# through as "expected to evolve" by not matching this set/prefix).
_STABILITY_EXPECTED_FIELDS = {"alive_status", "status", "canonical_name", "owner"}
_STABILITY_EXPECTED_PREFIXES = ("physical_",)


@dataclass
class ValidationResult:
    """Outcome of gating a proposed new/updated entity."""
    accepted: bool
    reason: str
    confidence: Optional[float] = None  # possibly downgraded confidence, when accepted


@dataclass
class ContradictionResult:
    """Outcome of checking one field's proposed change against its current value."""
    is_contradiction: bool
    should_apply: bool  # whether the new value should still be written despite the contradiction
    description: str = ""


class ValidationEngine:
    """Gatekeeper for LLM-authored proposals before they reach NarrativeState."""

    def __init__(self, config=None):
        self._config = config
        self._min_confidence = 0.3
        if config and hasattr(config, "get"):
            self._min_confidence = config.get("narrative_state.min_confidence", 0.3)

    # ------------------------------------------------------------------
    # Entity-level gating (new characters / world items / relationship parties)
    # ------------------------------------------------------------------

    def evaluate_entity_proposal(
        self,
        entity_id: str,
        mention_hint: str,
        is_new: bool,
        confidence: float,
        chapter_data: Any,
        flagged_entity_ids: Set[str],
    ) -> ValidationResult:
        """Decide whether a proposed entity update should be accepted, and at what confidence."""
        if confidence < self._min_confidence:
            return ValidationResult(False, f"confidence {confidence:.2f} below minimum {self._min_confidence:.2f}")

        flagged = entity_id.lower() in flagged_entity_ids or (mention_hint or "").lower() in flagged_entity_ids

        if not is_new:
            # Interpreting/evolving something already established is expected reasoning, not
            # a hallucination risk — but still respect the consistency checker's own signal.
            if flagged:
                return ValidationResult(
                    True, "existing entity, but consistency checker flagged it this chapter",
                    confidence=max(0.0, confidence - 0.2),
                )
            return ValidationResult(True, "existing entity, no fresh evidence required")

        supported = self._is_evidence_supported(mention_hint, chapter_data)

        if flagged and not supported:
            return ValidationResult(False, "new entity flagged by consistency checker and not independently evidence-supported")
        if flagged:
            return ValidationResult(True, "flagged by consistency checker, but independently evidence-supported", confidence=max(0.0, confidence - 0.2))
        if not supported:
            if confidence < 0.6:
                return ValidationResult(False, "new entity with no deterministic evidence support and confidence below 0.6")
            return ValidationResult(True, "no deterministic evidence found, but confidence high enough to accept provisionally", confidence=round(confidence * 0.85, 4))

        return ValidationResult(True, "new entity supported by deterministic evidence")

    def _is_evidence_supported(self, mention_hint: str, chapter_data: Any) -> bool:
        """Whether a candidate name/mention appears anywhere in this chapter's deterministic evidence."""
        needle = (mention_hint or "").strip().lower()
        if not needle:
            return False

        def overlaps(text: Optional[str]) -> bool:
            if not text:
                return False
            text = text.strip().lower()
            return bool(text) and (needle in text or text in needle)

        for e in getattr(chapter_data, "entities", []):
            if overlaps(e.text):
                return True
        for cluster in getattr(chapter_data, "coreferences", []):
            if any(overlaps(m) for m in cluster.mentions):
                return True
        for rel in getattr(chapter_data, "relations", []):
            if overlaps(rel.subject) or overlaps(rel.object):
                return True
        for d in getattr(chapter_data, "dialogues", []):
            if overlaps(d.speaker):
                return True
        return False

    # ------------------------------------------------------------------
    # Field-level contradiction checking (generalizes the old character-only reconciliation)
    # ------------------------------------------------------------------

    def check_field_contradiction(
        self,
        field_key: str,
        old_value: Any,
        old_confidence: float,
        new_value: Any,
        new_confidence: float,
    ) -> ContradictionResult:
        """Check a proposed field change against its current value.

        Applies uniformly to any StateEntry field on any entity type. Fields expected to
        stay stable (physical traits, alive/status, canonical name, object ownership) that
        change without the new evidence outranking the old are flagged and, if the new
        evidence is weaker, suppressed rather than written. Fields expected to evolve
        freely are always allowed through.
        """
        if old_value is None or old_value == new_value:
            return ContradictionResult(False, True)

        is_stability_field = field_key in _STABILITY_EXPECTED_FIELDS or any(
            field_key.startswith(p) for p in _STABILITY_EXPECTED_PREFIXES
        )
        if not is_stability_field:
            return ContradictionResult(False, True)

        if new_confidence < old_confidence:
            return ContradictionResult(
                True, False,
                f"'{field_key}' changed from {old_value!r} (confidence {old_confidence:.2f}) to "
                f"{new_value!r} (confidence {new_confidence:.2f}) — lower-confidence contradiction suppressed."
            )

        return ContradictionResult(
            True, True,
            f"'{field_key}' changed from {old_value!r} (confidence {old_confidence:.2f}) to "
            f"{new_value!r} (confidence {new_confidence:.2f}) — accepted (confidence held or rose) but flagged."
        )
