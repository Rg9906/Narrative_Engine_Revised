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
from src.utils.llm_provider import LLMProvider

logger = logging.getLogger("NarrativeEngine.Engines.Editorial")


class EditorialEngine:
    """Runs a set of inspectors over NarrativeState and StateDelta to produce an editorial report."""

    def __init__(self, config=None):
        self._config = config
        self._llm = LLMProvider(config)
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

    def review(self, state: NarrativeState, delta: StateDelta | None = None, raw_text: str = "") -> dict:
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

        # Run LLM-based critique (Gemini / Groq / Ollama — auto-detected)
        try:
            llm_findings = self._run_llm_critique(state, delta, raw_text=raw_text)
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
                "llm_provider": self._llm.provider_name,
            },
            "findings": norm,
        }

        out_dir = Path(self._config.memory_dir) if (self._config and getattr(self._config, 'memory_dir', None)) else Path('data') / 'memory'
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"editorial_report_ch{report['metadata']['chapter']}.json"
        tmp_file = out_file.with_suffix(".json.tmp")
        with open(tmp_file, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        import os
        os.replace(tmp_file, out_file)

        return report

    def _run_llm_critique(self, state: NarrativeState, delta: StateDelta | None, raw_text: str = "") -> List[dict]:
        if not self._llm.is_available:
            logger.info(f"No LLM provider available (provider: {self._llm.provider_name}). Skipping LLM critique.")
            return []

        # Prepare narrative state summary for LLM context
        char_list = []
        for cid, cdata in state.characters.items():
            name = cid
            if "canonical_name" in cdata and cdata["canonical_name"].current:
                name = cdata["canonical_name"].current.value
            goals = cdata.get("goals").current.value if "goals" in cdata and cdata["goals"].current else "unknown"
            fears = cdata.get("fears").current.value if "fears" in cdata and cdata["fears"].current else "unknown"
            traits = cdata.get("personality_traits").current.value if "personality_traits" in cdata and cdata["personality_traits"].current else []
            char_list.append(f"- Character '{name}' (Aliases: {cid}): Goals: {goals}, Fears: {fears}, Personality: {traits}")

        # Active relationship statuses
        relations = []
        for rid, rdata in state.relationships.items():
            label = rdata.get("relationship_label").current.value if "relationship_label" in rdata and rdata["relationship_label"].current else "unknown"
            char_parts = rid.split("::")
            relations.append(f"- Relationship between '{char_parts[0]}' and '{char_parts[1]}': Status: {label}")

        # Count unresolved promises
        promises = []
        for pid, pdata in state.promises.items():
            status = pdata.get("status").current.value if "status" in pdata and pdata["status"].current else "unresolved"
            if status in ("unresolved", "OPEN"):
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
            f"--- Current Chapter Raw Text ---\n"
            f"{raw_text if raw_text else 'No raw text provided.'}\n\n"
            f"--- Current Story Memory State ---\n"
            f"Characters tracked (Goals, Fears, Personality):\n" + ("\n".join(char_list) if char_list else "None") + "\n\n"
            f"Unresolved promises/foreshadows:\n" + ("\n".join(promises) if promises else "None") + "\n\n"
            f"Active relationship statuses:\n" + ("\n".join(relations) if relations else "None") + "\n\n"
            f"Unresolved mysteries & conflict events:\n" + ("\n".join(mysteries) if mysteries else "None") + "\n\n"
            f"--- Editorial Instructions ---\n"
            f"Please critique the current chapter based on the provided story memory state. Specifically, critique:\n"
            f"1. **Thematic Pacing Drift**: Analyze whether the chapter's pacing is consistent with the current narrative arc or if it introduces sudden shifts, drag, or rushed scenes.\n"
            f"2. **Stylistic Variance**: Detect if there is a noticeable stylistic, voice, or tone variance in this chapter compared to the standard narrative flow.\n"
            f"3. **Mystery/Conflict cross-referencing**: Cross-reference newly emerged conflict events from mysteries (e.g. contradiction events, inventory dual-ownership, or physical description mismatches) to flag contradictions.\n\n"
            f"Format your response EXACTLY as a JSON array of objects. Do not include markdown code block syntax (like ```json). "
            f"Each object must have the following fields:\n"
            f"- 'severity': 'error' | 'warning' | 'suggestion' | 'note'\n"
            f"- 'category': 'consistency' | 'pacing' | 'character' | 'arc' | 'theme' | 'voice'\n"
            f"- 'title': A short, clear headline for the issue.\n"
            f"- 'description': Detailed developmental editor feedback.\n"
            f"- 'confidence': Float value between 0.0 and 1.0.\n"
        )

        messages = [
            {"role": "system", "content": "You are a professional developmental editor. You communicate findings strictly as a JSON array of objects. Never include explanations, markdown code block backticks (like ```json), or intro/outro text. The response must be pure JSON."},
            {"role": "user", "content": prompt}
        ]

        try:
            logger.info(f"Running LLM developmental editor critique via {self._llm.provider_name} (model: {self._llm.model})...")
            raw_output = self._llm.chat(messages)
            return self._parse_json_findings(raw_output, state.last_processed_chapter)
        except Exception as e:
            logger.error(f"Error during {self._llm.provider_name} LLM critique: {e}")
            return []

    def _parse_json_findings(self, raw_output: str, chapter_num: int) -> List[dict]:
        """Clean and parse JSON output from the LLM, handling conversational wrapping."""
        cleaned_output = raw_output.strip()

        # Try regex to locate outermost JSON array structure [...]
        import re
        array_match = re.search(r'(\[.*\])', cleaned_output, re.DOTALL)
        if array_match:
            candidate = array_match.group(1).strip()
            try:
                # Test if it parses correctly
                llm_findings = json.loads(candidate)
                if isinstance(llm_findings, list):
                    cleaned_output = candidate
            except Exception:
                pass
        else:
            # If no array found, try to locate outermost JSON object structure {...}
            obj_match = re.search(r'(\{.*\})', cleaned_output, re.DOTALL)
            if obj_match:
                candidate = obj_match.group(1).strip()
                try:
                    llm_findings = json.loads(candidate)
                    if isinstance(llm_findings, dict):
                        cleaned_output = candidate
                except Exception:
                    pass

        # If regex search failed or didn't yield a valid structure, fallback to standard markdown stripping
        if cleaned_output == raw_output.strip() and cleaned_output.startswith("```"):
            lines = cleaned_output.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_output = "\n".join(lines).strip()

        # Parse findings
        llm_findings = json.loads(cleaned_output)
        
        # Coerce to a list of dicts
        if isinstance(llm_findings, dict):
            llm_findings = [llm_findings]
        elif not isinstance(llm_findings, list):
            raise ValueError("LLM response did not parse into a list or dict of findings.")

        normalized_findings = []
        for lf in llm_findings:
            if not isinstance(lf, dict):
                continue
            lf["chapter"] = chapter_num
            lf["evidence_ids"] = lf.get("evidence_ids", [])
            lf["related_entities"] = lf.get("related_entities", [])
            normalized_findings.append(lf)
        return normalized_findings

