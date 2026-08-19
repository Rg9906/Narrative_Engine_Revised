"""Read-only access to editorial_report_ch{N}.json files."""

from __future__ import annotations

import json
import re
from typing import Any

from src.utils.config import Config

REPORT_FILE_RE = re.compile(r"editorial_report_ch(\d+)\.json$")


def list_reports(config: Config) -> list[dict[str, Any]]:
    reports_dir = config.reports_dir
    if not reports_dir.exists():
        return []

    summaries: list[dict[str, Any]] = []
    for path in reports_dir.glob("editorial_report_ch*.json"):
        match = REPORT_FILE_RE.search(path.name)
        if not match:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        findings = report.get("findings", []) or []
        top_findings = report.get("top_findings", []) or []

        # Severity counts describe the RANKED findings when a synthesis pass produced
        # them, falling back to raw findings for reports generated before that existed.
        # Counting raw findings on a synthesized report would report a chapter as having
        # e.g. 57 "note"s when the review's actual conclusion is five ranked issues.
        counted = top_findings if top_findings else findings
        severity_counts: dict[str, int] = {}
        for finding in counted:
            severity = str(finding.get("severity", "note")).lower()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        summaries.append(
            {
                "chapter": int(match.group(1)),
                "generated_at": report.get("metadata", {}).get("generated_at"),
                "inspector_count": report.get("metadata", {}).get("inspector_count"),
                "llm_provider": report.get("metadata", {}).get("llm_provider"),
                "finding_count": len(counted),
                "raw_finding_count": len(findings),
                "signal_group_count": len(report.get("signals", []) or []),
                "has_letter": bool(str(report.get("editorial_letter") or "").strip()),
                "severity_counts": severity_counts,
            }
        )

    summaries.sort(key=lambda r: r["chapter"], reverse=True)
    return summaries


def get_report(config: Config, chapter: int) -> dict[str, Any] | None:
    path = config.reports_dir / f"editorial_report_ch{chapter}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
