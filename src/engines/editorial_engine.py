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
from src.review.relationship_inspector import RelationshipInspector
from src.review.timeline_inspector import TimelineInspector
from src.review.conflict_inspector import ConflictInspector
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
            RelationshipInspector(),
            TimelineInspector(),
            ConflictInspector(),
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

        # Run LLM-based critique (OpenAI integration)
        try:
            llm_findings = self._run_llm_critique(state, delta)
            findings.extend(llm_findings)
        except Exception as e:
            logger.error(f"Failed to run LLM critique: {e}")

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

    def _run_llm_critique(self, state: NarrativeState, delta: StateDelta | None) -> List[dict]:
        import os
        import json
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.info("OPENAI_API_KEY not found in environment. Skipping LLM critique.")
            return []

        try:
            logger.info("Running OpenAI LLM developmental editor critique...")
            # Prepare narrative state summary for LLM context
            char_list = []
            for cid, cdata in state.characters.items():
                name = cid
                if "canonical_name" in cdata and cdata["canonical_name"].current:
                    name = cdata["canonical_name"].current.value
                goals = cdata.get("goal").current.value if "goal" in cdata and cdata["goal"].current else "unknown"
                traits = cdata.get("personality_traits").current.value if "personality_traits" in cdata and cdata["personality_traits"].current else []
                char_list.append(f"- Character '{name}' (Aliases: {cid}): Goals: {goals}, Personality: {traits}")

            # Count unresolved promises
            promises = []
            for pid, pdata in state.promises.items():
                status = pdata.get("status").current.value if "status" in pdata and pdata["status"].current else "unresolved"
                if status == "unresolved":
                    text = pdata.get("promise_text").current.value if "promise_text" in pdata and pdata["promise_text"].current else ""
                    promises.append(f"- {text} (Chapter {pdata.get('chapter_made').current.value if 'chapter_made' in pdata and pdata['chapter_made'].current else 'unknown'})")

            mysteries = []
            for mid, mdata in state.mysteries.items():
                status = mdata.get("status").current.value if "status" in mdata and mdata["status"].current else "unresolved"
                if status == "unresolved":
                    text = mdata.get("mystery_text").current.value if "mystery_text" in mdata and mdata["mystery_text"].current else ""
                    mysteries.append(f"- {text} (Chapter {mdata.get('chapter_introduced').current.value if 'chapter_introduced' in mdata and mdata['chapter_introduced'].current else 'unknown'})")

            prompt = (
                f"You are a developmental editor reviewing Chapter {state.last_processed_chapter}.\n\n"
                f"Chapter State Delta Summary:\n{delta.summary if delta else 'No delta summary'}\n\n"
                f"Story Memory State:\n"
                f"Characters tracked:\n" + "\n".join(char_list) + "\n\n"
                f"Unresolved promises/foreshadows:\n" + "\n".join(promises) + "\n\n"
                f"Unresolved mysteries:\n" + "\n".join(mysteries) + "\n\n"
                f"Please review the chapter changes and story memory. Identify any pacing issues, character inconsistency, weak motivations, or unresolved plots.\n\n"
                f"Format your response EXACTLY as a JSON array of objects. Do not include markdown code block syntax (like ```json). "
                f"Each object must have the following fields:\n"
                f"- 'severity': 'error' | 'warning' | 'suggestion' | 'note'\n"
                f"- 'category': 'consistency' | 'pacing' | 'character' | 'arc' | 'theme' | 'voice'\n"
                f"- 'title': A short, clear headline for the issue.\n"
                f"- 'description': Detailed developmental editor feedback.\n"
                f"- 'confidence': Float value between 0.0 and 1.0.\n"
            )

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional developmental editor. You communicate findings strictly as a JSON array. Never include explanations, intro/outro text, or markdown code block formatting in your response."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )

            raw_output = response.choices[0].message.content.strip()
            # Clean up markdown JSON wrapper blocks if the LLM outputted them anyway
            if raw_output.startswith("```"):
                lines = raw_output.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_output = "\n".join(lines).strip()

            llm_findings = json.loads(raw_output)
            normalized_findings = []
            for lf in llm_findings:
                # Add chapter number
                lf["chapter"] = state.last_processed_chapter
                lf["evidence_ids"] = lf.get("evidence_ids", [])
                lf["related_entities"] = lf.get("related_entities", [])
                normalized_findings.append(lf)

            logger.info(f"OpenAI LLM critique returned {len(normalized_findings)} findings.")
            return normalized_findings
        except Exception as e:
            logger.error(f"Error during OpenAI LLM critique: {e}")
            return []
