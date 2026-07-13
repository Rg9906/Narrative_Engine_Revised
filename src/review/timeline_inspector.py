"""
Timeline Inspector — Checks chronological consistency and post-mortem actions.

Implementation: Phase 11
"""

from src.review.inspector import BaseInspector, Finding
from typing import List
import re


class TimelineInspector(BaseInspector):
    """Inspects the story timeline for continuity errors, timeline jumps, or deceased character actions."""

    @property
    def name(self) -> str:
        return "Timeline Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        # 1. Check for chronological order anomaly (Timeline jumps/flashbacks)
        prev_chapter = 0
        for idx, event in enumerate(state.timeline):
            evt_chap = event.get("chapter", 0)
            if evt_chap < prev_chapter:
                findings.append(Finding(
                    severity='note',
                    category='consistency',
                    title='Timeline jump detected',
                    description=(
                        f"Event '{event.get('subject')} {event.get('predicate')} {event.get('object')}' "
                        f"in chapter {evt_chap} occurs after events from chapter {prev_chapter}. "
                        f"This indicates a flashback or non-linear timeline sequence."
                    ),
                    chapter=chapter,
                    evidence_ids=[],
                    related_entities=[event.get("subject")] if event.get("subject") else [],
                    confidence=0.6,
                ))
            prev_chapter = max(prev_chapter, evt_chap)

        # 2. Check for post-mortem actions (deceased characters performing actions later)
        # Scan for death indicators in timeline
        death_chapters = {}
        death_keywords = {"dies", "died", "killed", "slain", "murdered", "perishes"}
        
        for event in state.timeline:
            subj = (event.get("subject") or "").lower()
            pred = (event.get("predicate") or "").lower()
            obj = (event.get("object") or "").lower()
            evt_chap = event.get("chapter", 0)

            # Check if subject died
            if any(k in pred or k in obj for k in death_keywords):
                if subj and subj not in death_chapters:
                    death_chapters[subj] = evt_chap

        # Scan for actions by deceased characters in later chapters
        for event in state.timeline:
            subj = (event.get("subject") or "").lower()
            evt_chap = event.get("chapter", 0)

            if subj in death_chapters:
                death_chap = death_chapters[subj]
                if evt_chap > death_chap:
                    # Deceased character is acting in a later chapter!
                    findings.append(Finding(
                        severity='error',
                        category='consistency',
                        title='Post-mortem action anomaly',
                        description=(
                            f"Deceased character '{event.get('subject')}' (died in chapter {death_chap}) "
                            f"is performing an action '{event.get('predicate')} {event.get('object')}' "
                            f"in later chapter {evt_chap}."
                        ),
                        chapter=chapter,
                        evidence_ids=[],
                        related_entities=[event.get("subject")],
                        confidence=0.85,
                    ))

        return findings
