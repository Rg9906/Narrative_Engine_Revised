"""
Relationship Inspector — Checks character relationship dynamics for abrupt changes.

Implementation: Phase 11
"""

from src.review.inspector import BaseInspector, Finding
from typing import List


class RelationshipInspector(BaseInspector):
    """Inspects character relationships for abrupt shifts or inconsistencies."""

    @property
    def name(self) -> str:
        return "Relationship Inspector"

    def inspect(self, state, delta) -> List[Finding]:
        findings: List[Finding] = []
        chapter = state.last_processed_chapter

        for rel_id, entries in state.relationships.items():
            label_entry = entries.get('relationship_label')
            if label_entry and label_entry.current:
                current_label = label_entry.current.value
                # Check history for abrupt jumps
                for snapshot in label_entry.history:
                    prev_label = snapshot.value
                    if prev_label != current_label:
                        abrupt = False
                        # Check for direct Enemy <-> Romantic jumps
                        if (prev_label == "ENMITY" and current_label == "ROMANTIC") or \
                           (prev_label == "ROMANTIC" and current_label == "ENMITY"):
                            abrupt = True
                        
                        if abrupt:
                            char_parts = rel_id.split("::")
                            findings.append(Finding(
                                severity='warning',
                                category='consistency',
                                title='Abrupt relationship shift',
                                description=(
                                    f"Relationship between '{char_parts[0]}' and '{char_parts[1]}' shifted abruptly "
                                    f"from {prev_label} (chapter {snapshot.chapter}) to {current_label} (chapter {label_entry.current.chapter}) "
                                    f"without gradual transition."
                                ),
                                chapter=chapter,
                                evidence_ids=list(set((getattr(snapshot, 'evidence_ids', []) or []) + (getattr(label_entry.current, 'evidence_ids', []) or []))),
                                related_entities=char_parts,
                                confidence=0.75,
                            ))
                            break

        return findings
