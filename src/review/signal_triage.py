"""
Signal Triage — Collapses raw inspector output into distinct editorial signals.

The nine rule-based inspectors emit one Finding per offending entity, which is the
right granularity for a detector and the wrong granularity for a report. A single
misfiring detector could dominate an entire chapter's review: chapter 3's report
contained 81 findings, of which 50 were the identical note "Abrupt mystery
resolution" (one per junk mystery) and 16 were "Character X is only mentioned 1
time(s)" (one per character). Six of the 81 came from the LLM. Reading that report,
the loudest thing in it was whichever detector happened to be noisiest — not
whichever problem mattered most.

This module groups findings that are the same observation about different entities
into one signal carrying a count and a few exemplars. Crucially, a signal's priority
does NOT scale with how many entities tripped it: fifty identical notes are one
observation repeated fifty times, and usually evidence of an over-eager detector
rather than fifty independent story problems. That grouping is what the LLM
synthesis stage reasons over, and what keeps its prompt from being 90% duplicates.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Relative weight of each severity level when ranking signals.
SEVERITY_WEIGHT = {
    "error": 4.0,
    "warning": 3.0,
    "suggestion": 2.0,
    "note": 1.0,
}

# Exemplars retained per signal group. Enough to show the shape of the problem
# without reproducing every instance.
MAX_EXEMPLARS = 3

# A group larger than this is treated as a probable detector-calibration problem and
# flagged as such, so a human reads "one noisy rule" rather than "N story problems".
NOISY_GROUP_THRESHOLD = 12


def _severity_of(finding: Dict[str, Any]) -> str:
    return str(finding.get("severity", "note")).strip().lower() or "note"


def group_signals(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse findings into distinct signals, ranked most important first.

    Findings are grouped by (category, title) — the pair that identifies *which
    observation* was made, independent of which entity tripped it.
    """
    groups: Dict[tuple, Dict[str, Any]] = {}

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        category = str(finding.get("category", "uncategorized"))
        title = str(finding.get("title", "Untitled finding"))
        key = (category, title)

        group = groups.get(key)
        if group is None:
            group = {
                "category": category,
                "title": title,
                "severity": _severity_of(finding),
                "count": 0,
                "examples": [],
                "related_entities": [],
                "evidence_ids": [],
                "confidences": [],
            }
            groups[key] = group

        group["count"] += 1

        # A group takes the highest severity any of its members reported, so grouping
        # can never quietly downgrade a real error into a note.
        if SEVERITY_WEIGHT.get(_severity_of(finding), 1.0) > SEVERITY_WEIGHT.get(group["severity"], 1.0):
            group["severity"] = _severity_of(finding)

        if len(group["examples"]) < MAX_EXEMPLARS:
            description = str(finding.get("description") or "").strip()
            if description:
                group["examples"].append(description)

        for entity in finding.get("related_entities") or []:
            if isinstance(entity, str) and entity and entity not in group["related_entities"]:
                group["related_entities"].append(entity)
        for evidence_id in finding.get("evidence_ids") or []:
            if isinstance(evidence_id, str) and evidence_id not in group["evidence_ids"]:
                group["evidence_ids"].append(evidence_id)

        try:
            group["confidences"].append(float(finding.get("confidence", 1.0)))
        except (TypeError, ValueError):
            pass

    signals: List[Dict[str, Any]] = []
    for group in groups.values():
        confidences = group.pop("confidences") or [1.0]
        mean_confidence = sum(confidences) / len(confidences)
        group["confidence"] = round(mean_confidence, 3)
        # Priority is severity x confidence and deliberately ignores `count`. See the
        # module docstring: repetition across entities is not evidence of importance.
        group["priority"] = round(SEVERITY_WEIGHT.get(group["severity"], 1.0) * mean_confidence, 3)
        group["likely_detector_noise"] = group["count"] >= NOISY_GROUP_THRESHOLD
        group["suppressed_count"] = max(0, group["count"] - len(group["examples"]))
        signals.append(group)

    signals.sort(key=lambda s: (-s["priority"], -s["count"], s["title"]))
    return signals


def render_signals_for_prompt(signals: List[Dict[str, Any]], limit: int = 30) -> str:
    """Render grouped signals as a compact block for an LLM prompt.

    Bounded by `limit` so a pathological chapter can't grow the prompt without end.
    """
    if not signals:
        return "(no rule-based signals fired for this chapter)"

    lines: List[str] = []
    for index, signal in enumerate(signals[:limit], start=1):
        header = (
            f"{index}. [{signal['severity']}] {signal['category']} — {signal['title']} "
            f"(fired {signal['count']}x, confidence {signal['confidence']})"
        )
        if signal["likely_detector_noise"]:
            header += " [WARNING: fired very often — treat as one possibly-miscalibrated rule, not many separate problems]"
        lines.append(header)

        for example in signal["examples"]:
            lines.append(f"     - {example}")
        if signal["suppressed_count"]:
            lines.append(f"     - (+{signal['suppressed_count']} further instances not shown)")
        if signal["related_entities"]:
            entities = ", ".join(signal["related_entities"][:12])
            lines.append(f"     entities: {entities}")

    if len(signals) > limit:
        lines.append(f"... and {len(signals) - limit} lower-priority signal group(s) omitted.")

    return "\n".join(lines)
