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
from src.review.spatiotemporal_inspector import SpatiotemporalInspector
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
            SpatiotemporalInspector(),
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

        # Add LLM structural mysteries from delta if available
        if delta and hasattr(delta, 'structural_mysteries'):
            for mystery in delta.structural_mysteries:
                findings.append({
                    "severity": mystery.get("severity", "warning").lower(),
                    "category": "consistency",
                    "title": f"Structural contradiction: {mystery.get('issue_type')}",
                    "description": mystery.get("description"),
                    "chapter": delta.chapter_number,
                    "evidence_ids": [],
                    "related_entities": mystery.get("related_entities", []),
                    "confidence": 0.9,
                })

        # Surface ValidationEngine rejections (src/engines/validation_engine.py) — proposals
        # from the LLM extraction stages that never reached NarrativeState. Shown here rather
        # than only logged, so a human editor can see what the engine chose not to trust.
        if delta and hasattr(delta, 'rejected_proposals'):
            for rejected in delta.rejected_proposals:
                findings.append({
                    "severity": "note",
                    "category": "validation",
                    "title": f"Proposal rejected: {rejected.get('kind')}",
                    "description": rejected.get("reason"),
                    "chapter": delta.chapter_number,
                    "evidence_ids": [],
                    "related_entities": [rejected.get("entity_id")] if rejected.get("entity_id") else [],
                    "confidence": 1.0,
                })

        # Run LLM-based critique (Gemini / Groq / Ollama — auto-detected)
        key_events: List[str] = []
        try:
            llm_findings, key_events = self._run_llm_critique(state, delta, raw_text=raw_text)
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
            # A handful of human-readable story beats for the chapter, curated by the same
            # LLM critique call rather than the mechanical subject-verb-object triples in
            # state.timeline (which exist for structural inspectors like SpatiotemporalInspector
            # to reason over, not for a human to read as a narrative summary).
            "key_events": key_events,
        }

        # Only persist to disk when a real project config is supplied. There is no safe
        # generic fallback path here: callers with no config (unit tests, ad-hoc scripts)
        # have no project directory to anchor to, and a CWD-relative Path('data')/'reports'
        # default previously caused every pytest run to silently overwrite real chapter
        # editorial reports under the repo's own data/reports/ directory. Callers that want
        # a report on disk must pass a config with a reports_dir.
        if self._config and getattr(self._config, 'reports_dir', None):
            out_dir = Path(self._config.reports_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"editorial_report_ch{report['metadata']['chapter']}.json"
            tmp_file = out_file.with_suffix(".json.tmp")

            try:
                with open(tmp_file, 'w', encoding='utf-8') as fh:
                    json.dump(report, fh, indent=2, ensure_ascii=False)
                import os
                os.replace(tmp_file, out_file)
            except OSError as e:
                logger.warning(f"Atomic save of editorial report failed ({e}). Attempting direct write to {out_file}...")
                try:
                    with open(out_file, 'w', encoding='utf-8') as fh:
                        json.dump(report, fh, indent=2, ensure_ascii=False)
                except OSError as e2:
                    logger.error(f"Failed to write editorial report directly to {out_file}: {e2}")
        else:
            logger.info("No config provided; returning in-memory report without writing to disk.")

        return report

    def _run_llm_critique(self, state: NarrativeState, delta: StateDelta | None, raw_text: str = "") -> tuple[List[dict], List[str]]:
        if not self._llm.is_available:
            logger.info(f"No LLM provider available (provider: {self._llm.provider_name}). Skipping LLM critique.")
            return [], []

        # Reuse the same token-budgeted, single-source-of-truth context hydration every other
        # LLM call in this codebase uses (src/pipeline/llm_extraction.py's stages), instead of a
        # separate ad hoc, unbounded serialization. This is what actually gives the critique
        # cross-chapter awareness: ContextRetriever's <ChapterSummaries> and <RecentTimeline>
        # tiers carry accumulated history forward, which the prior inline version never
        # included at all — it only ever saw the current chapter's raw text against the
        # current-moment state, with nothing preventing unbounded prompt growth as the novel
        # (and the number of characters/relationships/promises) grows over many chapters.
        from src.pipeline.context_retriever import ContextRetriever
        context_block, _ = ContextRetriever(self._config).retrieve_context(raw_text, current_state=state)

        # Unresolved mysteries aren't a ContextRetriever tier (they're not filtered by whether
        # they're textually "active" in this chapter — an editor should see ALL open mysteries
        # regardless), so they're still built directly here.
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
            f"--- Story Memory (accumulated across all prior chapters) ---\n"
            f"{context_block if context_block else 'No prior story memory yet — this is likely the first chapter.'}\n\n"
            f"Unresolved mysteries & conflict events:\n" + ("\n".join(mysteries) if mysteries else "None") + "\n\n"
            f"--- Editorial Instructions ---\n"
            f"Please critique the current chapter based on the provided story memory, reasoning across the "
            f"accumulated chapter summaries and recent timeline above — not just this chapter in isolation. "
            f"Specifically, critique:\n"
            f"1. **Thematic Pacing Drift**: Analyze whether the chapter's pacing is consistent with the narrative "
            f"arc established across prior chapters, or if it introduces sudden shifts, drag, or rushed scenes.\n"
            f"2. **Stylistic Variance**: Detect if there is a noticeable stylistic, voice, or tone variance in this "
            f"chapter compared to the standard narrative flow.\n"
            f"3. **Mystery/Conflict cross-referencing**: Cross-reference newly emerged conflict events from "
            f"mysteries (e.g. contradiction events, inventory dual-ownership, or physical description mismatches) "
            f"to flag contradictions.\n\n"
            f"Also summarize the chapter's key events: 3-8 short, plain-English sentences describing what actually "
            f"happened in this chapter that a reader would care about (plot-significant actions, revelations, "
            f"decisions, arrivals/departures) — not every sentence-level action. This is meant to replace a "
            f"mechanical list of every extracted subject-verb-object triple with something an editor or reader "
            f"would actually want to read.\n\n"
            f"Format your response EXACTLY as a single JSON object (not an array). Do not include markdown code "
            f"block syntax (like ```json). The object must have exactly two fields:\n"
            f"- 'findings': a JSON array of objects, each with:\n"
            f"  - 'severity': 'error' | 'warning' | 'suggestion' | 'note'\n"
            f"  - 'category': 'consistency' | 'pacing' | 'character' | 'arc' | 'theme' | 'voice'\n"
            f"  - 'title': A short, clear headline for the issue.\n"
            f"  - 'description': Detailed developmental editor feedback.\n"
            f"  - 'confidence': Float value between 0.0 and 1.0.\n"
            f"- 'key_events': a JSON array of 3-8 short plain-English strings, as described above.\n"
        )

        messages = [
            {"role": "system", "content": "You are a professional developmental editor. You communicate strictly as a single JSON object with 'findings' and 'key_events' fields. Never include explanations, markdown code block backticks (like ```json), or intro/outro text. The response must be pure JSON."},
            {"role": "user", "content": prompt}
        ]

        try:
            logger.info(f"Running LLM developmental editor critique via {self._llm.provider_name} (model: {self._llm.model})...")
            raw_output = self._llm.chat(messages)
            return self._parse_json_findings(raw_output, state.last_processed_chapter)
        except Exception as e:
            logger.error(f"Error during {self._llm.provider_name} LLM critique: {e}")
            return [], []

    def _parse_json_findings(self, raw_output: str, chapter_num: int) -> tuple[List[dict], List[str]]:
        """Clean and parse JSON output from the LLM, handling conversational wrapping.

        Expected shape is a single object: {"findings": [...], "key_events": [...]}. Older
        prompts (and occasional LLM non-compliance) produced a bare findings array instead —
        still accepted for backward compatibility, just with no key_events.
        """
        cleaned_output = raw_output.strip()

        # Try regex to locate outermost JSON object structure {...} first — that's the
        # expected top-level shape now — falling back to an array for older/non-compliant
        # responses.
        import re
        obj_match = re.search(r'(\{.*\})', cleaned_output, re.DOTALL)
        parsed = None
        if obj_match:
            candidate = obj_match.group(1).strip()
            try:
                parsed = json.loads(candidate)
                cleaned_output = candidate
            except Exception:
                parsed = None

        if parsed is None:
            array_match = re.search(r'(\[.*\])', cleaned_output, re.DOTALL)
            if array_match:
                candidate = array_match.group(1).strip()
                try:
                    parsed = json.loads(candidate)
                    cleaned_output = candidate
                except Exception:
                    parsed = None

        if parsed is None:
            # Fallback to standard markdown code-fence stripping, then a final parse attempt.
            if cleaned_output.startswith("```"):
                lines = cleaned_output.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_output = "\n".join(lines).strip()
            parsed = json.loads(cleaned_output)

        if isinstance(parsed, dict) and "findings" in parsed:
            llm_findings = parsed.get("findings") or []
            key_events = parsed.get("key_events") or []
        elif isinstance(parsed, list):
            llm_findings = parsed
            key_events = []
        elif isinstance(parsed, dict):
            # A single finding object with no 'findings' wrapper — old fallback shape.
            llm_findings = [parsed]
            key_events = []
        else:
            raise ValueError("LLM response did not parse into a findings object, array, or dict.")

        normalized_findings = []
        for lf in llm_findings:
            if not isinstance(lf, dict):
                continue
            lf["chapter"] = chapter_num
            lf["evidence_ids"] = lf.get("evidence_ids", [])
            lf["related_entities"] = lf.get("related_entities", [])
            normalized_findings.append(lf)

        normalized_events = [str(e).strip() for e in key_events if str(e).strip()] if isinstance(key_events, list) else []

        return normalized_findings, normalized_events

