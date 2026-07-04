"""
Scene Inspector — Checks scene structure and pacing over state.

Implementation: Phase 10
"""

from src.review.inspector import BaseInspector, Finding
from typing import List
from src.models.state import NarrativeElementType


class SceneInspector(BaseInspector):
    """Inspects scene state for pacing, structure, and conflict issues."""

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

        # Count timeline events for the last processed chapter
        try:
            timeline_count = len([e for e in state.timeline if e.get('chapter') == chapter])
            if timeline_count > 10:
                findings.append(Finding(
                    severity='warning',
                    category='scene',
                    title='Dense timeline events',
                    description=f'This chapter has {timeline_count} timeline events; consider breaking into clearer scenes for pacing.',
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[],
                    confidence=0.6,
                ))
        except Exception:
            pass

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
