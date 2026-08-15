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
        severity_counts: dict[str, int] = {}
        for finding in findings:
            severity = str(finding.get("severity", "note")).lower()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        summaries.append(
            {
                "chapter": int(match.group(1)),
                "generated_at": report.get("metadata", {}).get("generated_at"),
                "inspector_count": report.get("metadata", {}).get("inspector_count"),
                "llm_provider": report.get("metadata", {}).get("llm_provider"),
                "finding_count": len(findings),
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
