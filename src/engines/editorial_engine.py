"""
Editorial Engine — Reasons over Narrative State, not raw text.

The editorial engine is the critique layer. It inspects the evolving
narrative state and compares:
  - Current state vs. previous state
  - Expected state vs. actual state
  - Historical trends and graph structure
  - Evidence consistency

It does NOT re-read the chapter text. It reasons over structured state.

Implementation: Phase 10
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from src.review.char_inspector import CharacterInspector
from src.review.scene_inspector import SceneInspector
from src.review.pacing_inspector import PacingInspector
from src.review.voice_inspector import VoiceInspector
from src.review.arc_inspector import ArcInspector
from src.models.state import NarrativeState, StateDelta

logger = logging.getLogger("NarrativeEngine.Engines.Editorial")


class EditorialEngine:
    """Runs a set of inspectors over NarrativeState and StateDelta to produce an editorial report."""

    def __init__(self, config=None):
        self._config = config
        self.inspectors = [
            CharacterInspector(),
            SceneInspector(),
            PacingInspector(),
            VoiceInspector(),
            ArcInspector(),
        ]

    def review(self, state: NarrativeState, delta: StateDelta | None = None) -> dict:
        findings = []
        for inspector in self.inspectors:
            try:
                f = inspector.inspect(state, delta)
                findings.extend(f)
            except Exception as e:
                findings.append({
                    "severity": "error",
                    "category": "inspector",
                    "title": f"Inspector error: {inspector.name}",
                    "description": str(e),
                    "chapter": delta.chapter_number if delta else state.last_processed_chapter,
                    "evidence_ids": [],
                    "related_entities": [],
                    "confidence": 0.0,
                })

        # Normalize findings to dicts
        from dataclasses import asdict, is_dataclass

        norm = []
        for f in findings:
            if hasattr(f, 'to_dict'):
                norm.append(f.to_dict())
            elif is_dataclass(f):
                norm.append(asdict(f))
            else:
                norm.append(f)

        from datetime import datetime
        report = {
            "metadata": {
                "chapter": delta.chapter_number if delta else state.last_processed_chapter,
                "generated_at": datetime.now().isoformat(),
                "inspector_count": len(self.inspectors),
            },
            "findings": norm,
        }

        out_dir = Path(self._config.memory_dir) if (self._config and getattr(self._config, 'memory_dir', None)) else Path('data') / 'memory'
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"editorial_report_ch{report['metadata']['chapter']}.json"
        with open(out_file, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

        return report
