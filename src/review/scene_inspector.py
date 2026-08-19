"""
Scene Inspector — Checks scene structure and pacing over state.

Implementation: Phase 10
"""

from src.review.inspector import BaseInspector, Finding
from typing import List
from src.models.state import NarrativeElementType


class SceneInspector(BaseInspector):
    """Inspects scene state for pacing, structure, and conflict issues."""

    # Significant story beats in one chapter beyond which the chapter is likely
    # carrying too much plot. Counted against the curated timeline, whose own
    # extraction stage is capped at 8 beats per chapter.
    DENSE_BEAT_THRESHOLD = 7

    @property
    def name(self) -> str:
        return "Scene Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        """Inspect scene/timeline for pacing and scene detection issues.

        Rules implemented:
        - Warn if many timeline events occur within the same chapter (pacing)
        - Note if timeline events exist but no scenes were introduced by the SceneEngine
        """
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        # Count significant story beats for the last processed chapter. This reads the
        # CURATED timeline (LLM-authored narrative beats plus reader-facing structural
        # markers), not the raw dependency-parsed triples in state.raw_relations. When it
        # read the raw feed, a 279-word chapter registered "36 timeline events" and the
        # inspector advised breaking it into clearer scenes — a conclusion drawn entirely
        # from parser verbosity rather than from anything about the chapter's structure.
        try:
            beats = [
                e for e in state.timeline
                if e.get('chapter') == chapter and e.get('kind', 'narrative') == 'narrative'
            ]
            timeline_count = len(beats)
            if timeline_count > self.DENSE_BEAT_THRESHOLD:
                findings.append(Finding(
                    severity='warning',
                    category='scene',
                    title='Dense story beats',
                    description=(
                        f'This chapter carries {timeline_count} significant story beats. That is a '
                        f'lot of plot to land in one chapter; consider whether some of it wants '
                        f'more room, or clearer scene breaks between beats.'
                    ),
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[],
                    confidence=0.6,
                ))
        except Exception:
            timeline_count = 0

        # Detect whether any SCENE introductions occurred in the delta
        try:
            scene_introduced = False
            if delta is not None:
                for c in delta.changes:
                    if c.target_type == NarrativeElementType.SCENE:
                        scene_introduced = True
                        break
            if not scene_introduced and timeline_count > 0:
                findings.append(Finding(
                    severity='note',
                    category='scene',
                    title='No scene boundaries detected',
                    description='Timeline events were extracted but no scene boundaries were introduced. Consider explicit scene markers or stronger transitions.',
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[],
                    confidence=0.5,
                ))
        except Exception:
            pass

        return findings
