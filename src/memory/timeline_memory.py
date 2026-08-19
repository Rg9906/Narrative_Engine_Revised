"""
Timeline Memory — Chronological event tracking.

Implementation: Phase 8
"""

from src.memory.base_memory import BaseMemory


class TimelineMemory(BaseMemory):
    """Records deterministic relation evidence for the chapter.

    This memory used to manufacture one "timeline event" per dependency-parsed
    subject-verb-object triple and emit an INTRODUCTION StateChange for each. That
    was the same mistake `StateEngine` made when it appended those triples straight
    into `NarrativeState.timeline`: a triple is evidence, not a story beat. spaCy
    emits a row per verb/object pair, so a single descriptive sentence produced
    several "events", and a short chapter produced well over a hundred — swamping
    both the timeline and the chapter's change log with rows like
    "world moved sound".

    The curated chronology is now built by the World+Timeline LLM stage and applied
    in `StateEngine` (see `NarrativeState.timeline`); the raw triples are kept in
    `NarrativeState.raw_relations`. This class still records the triples as memory
    entries so the deterministic layer keeps a per-relation record, but it no longer
    reports them as narrative state changes — nothing downstream consumed those
    changes except the delta's own change count, which they inflated by roughly an
    order of magnitude.
    """

    def __init__(self, memory_file=None):
        super().__init__(memory_file)

    def update_from_chapter(self, chapter_data, chapter_num: int) -> list:
        """Record each extracted relation as a memory entry.

        Returns an empty change list by design — see the class docstring. Relations
        reach `NarrativeState.raw_relations` via `StateEngine`, and real events reach
        `NarrativeState.timeline` via the LLM timeline stage.
        """
        for idx, rel in enumerate(getattr(chapter_data, "relations", []), start=1):
            try:
                subj = rel.subject or ""
                pred = rel.predicate or ""
                obj = rel.object or ""
            except Exception:
                continue

            desc = f"{subj} {pred} {obj}".strip()
            if not desc:
                continue

            self.update_entry(
                f"ch{chapter_num}_rel{idx}", "description", desc, chapter=chapter_num,
                evidence_ids=[], confidence=0.8,
                reasoning="Dependency-parsed relation observed in chapter text.",
            )

        return []
