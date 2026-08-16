"""
Conflict Inspector — Inspects unresolved plot conflicts, neglected mysteries/promises, and conflict pacing.

Implementation: Phase 11
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class ConflictInspector(BaseInspector):
    """Inspects narrative conflicts (mysteries, promises) for resolution speed and neglect."""

    @property
    def name(self) -> str:
        return "Conflict Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        active_count = 0

        # 1. Check mysteries
        for mystery_id, mystery_fields in state.mysteries.items():
            status_entry = mystery_fields.get("status")
            intro_entry = mystery_fields.get("chapter_introduced")
            text_entry = mystery_fields.get("mystery_text")

            if not status_entry or not status_entry.current:
                continue

            status = status_entry.current.value
            intro_chap = intro_entry.current.value if intro_entry and intro_entry.current else 1
            mystery_text = text_entry.current.value if text_entry and text_entry.current else "Unknown mystery"

            if status == "unresolved":
                active_count += 1
                # Check for neglect (unresolved for > 5 chapters)
                if chapter - intro_chap > 5:
                    findings.append(Finding(
                        severity='warning',
                        category='conflict',
                        title='Neglected mystery / question',
                        description=(
                            f"The mystery '{mystery_text}' (introduced in chapter {intro_chap}) "
                            f"remains unresolved for {chapter - intro_chap} chapters. "
                            f"Consider dropping a clue or advancing this plot point."
                        ),
                        chapter=chapter,
                        evidence_ids=getattr(status_entry.current, 'evidence_ids', []),
                        confidence=0.8,
                    ))
            elif status == "resolved":
                # Field is written as "chapter_resolved" by MysteryMemory/PromiseMemory
                # (see _check_revelations / resolution handling) -- this used to read
                # "resolved_chapter" (reversed word order), which never matched, so
                # resolved_entry was always None and every resolved mystery/promise fell
                # back to res_chap == intro_chap, firing a false "Abrupt resolution"
                # finding regardless of when it was actually resolved. Caught by a
                # self-review pass.
                resolved_entry = mystery_fields.get("chapter_resolved")
                res_chap = resolved_entry.current.value if resolved_entry and resolved_entry.current else intro_chap
                # Check for abrupt resolution (resolved in same chapter)
                if res_chap == intro_chap:
                    findings.append(Finding(
                        severity='note',
                        category='conflict',
                        title='Abrupt mystery resolution',
                        description=(
                            f"The mystery '{mystery_text}' was introduced and resolved in the same chapter ({intro_chap}). "
                            f"Consider if building suspense across chapters would improve pacing."
                        ),
                        chapter=chapter,
                        evidence_ids=getattr(status_entry.current, 'evidence_ids', []),
                        confidence=0.7,
                    ))

        # 2. Check promises
        for promise_id, promise_fields in state.promises.items():
            status_entry = promise_fields.get("status")
            intro_entry = promise_fields.get("chapter_made")
            text_entry = promise_fields.get("promise_text")

            if not status_entry or not status_entry.current:
                continue

            status = status_entry.current.value
            intro_chap = intro_entry.current.value if intro_entry and intro_entry.current else 1
            promise_text = text_entry.current.value if text_entry and text_entry.current else "Unknown promise"

            if status == "unresolved":
                active_count += 1
                if chapter - intro_chap > 5:
                    findings.append(Finding(
                        severity='warning',
                        category='conflict',
                        title='Neglected narrative promise',
                        description=(
                            f"The promise/foreshadowing '{promise_text}' (made in chapter {intro_chap}) "
                            f"remains unresolved for {chapter - intro_chap} chapters. "
                            f"Ensure this promise is eventually paid off or broken with consequence."
                        ),
                        chapter=chapter,
                        evidence_ids=getattr(status_entry.current, 'evidence_ids', []),
                        confidence=0.8,
                    ))
            elif status in ("resolved", "broken"):
                # Same key-name mismatch as the mystery check above -- PromiseMemory
                # writes "chapter_resolved", not "resolved_chapter".
                resolved_entry = promise_fields.get("chapter_resolved")
                res_chap = resolved_entry.current.value if resolved_entry and resolved_entry.current else intro_chap
                if res_chap == intro_chap:
                    findings.append(Finding(
                        severity='note',
                        category='conflict',
                        title='Abrupt promise resolution',
                        description=(
                            f"The narrative promise '{promise_text}' was made and resolved/broken in the same chapter ({intro_chap}). "
                            f"Consider letting the promise linger longer to create expectation."
                        ),
                        chapter=chapter,
                        evidence_ids=getattr(status_entry.current, 'evidence_ids', []),
                        confidence=0.7,
                    ))

        # 3. Check overall conflict pacing (no active conflicts)
        if active_count == 0 and chapter > 2:
            findings.append(Finding(
                severity='suggestion',
                category='conflict',
                title='No active narrative drivers',
                description=(
                    f"As of chapter {chapter}, there are no active, unresolved mysteries or narrative promises. "
                    f"Consider introducing a new conflict or mystery to hook reader interest."
                ),
                chapter=chapter,
                evidence_ids=[],
                confidence=0.6,
            ))

        return findings
