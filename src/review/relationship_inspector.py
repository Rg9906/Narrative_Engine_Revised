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

                # Emotional Inversion Check (skipping from Nemesis to Allied without transition)
                trajectory = label_entry.get_trajectory()
                nemesis_stances = {"ENMITY", "RIVALRY", "NEMESIS"}
                allied_stances = {"ALLIANCE", "FRIENDSHIP", "ALLIED", "ROMANTIC"}
                
                for idx in range(1, len(trajectory)):
                    prev_snap = trajectory[idx - 1]
                    curr_snap = trajectory[idx]
                    
                    if prev_snap.value in nemesis_stances and curr_snap.value in allied_stances:
                        # Direct shift without transitional event in the history
                        char_parts = rel_id.split("::")
                        findings.append(Finding(
                            severity='warning',
                            category='consistency',
                            title='Emotional inversion warning',
                            description=(
                                f"Emotional Inversion: Stance between '{char_parts[0]}' and '{char_parts[1]}' jumped directly "
                                f"from '{prev_snap.value}' (chapter {prev_snap.chapter}) to '{curr_snap.value}' (chapter {curr_snap.chapter}) "
                                f"without mid-tier transitional interaction events."
                            ),
                            chapter=chapter,
                            evidence_ids=list(set((getattr(prev_snap, 'evidence_ids', []) or []) + (getattr(curr_snap, 'evidence_ids', []) or []))),
                            related_entities=char_parts,
                            confidence=0.8,
                        ))
                        break

        return findings
