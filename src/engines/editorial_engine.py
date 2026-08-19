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
from src.review.signal_triage import group_signals, render_signals_for_prompt
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

        # Normalize findings to dicts before triage, so grouping sees one uniform shape.
        from dataclasses import asdict, is_dataclass

        norm = []
        for f in findings:
            if hasattr(f, 'to_dict'):
                norm.append(f.to_dict())
            elif is_dataclass(f):
                norm.append(asdict(f))
            else:
                norm.append(f)

        # Collapse the rule-based output into distinct signals before any LLM sees it.
        # Nine inspectors emitting one finding per offending entity produced reports where
        # 50 of 81 findings were the same note repeated — see src/review/signal_triage.py.
        signals = group_signals(norm)
        # Captured before the LLM critique's findings are appended below, so it pairs
        # with signal_group_count: both describe the rule-based feed only.
        rule_based_count = len(norm)
        logger.info(f"Triaged {rule_based_count} rule-based findings into {len(signals)} distinct signal groups.")

        # Run LLM-based critique (Gemini / Groq / Ollama — auto-detected)
        key_events: List[str] = []
        llm_findings: List[dict] = []
        try:
            llm_findings, key_events = self._run_llm_critique(state, delta, raw_text=raw_text)
            norm.extend(llm_findings)
        except Exception as e:
            logger.error(f"Failed to run LLM critique: {e}")

        # A chapter's story beats should never silently vanish. When the critique call
        # fails or omits key_events (which is exactly what happened to chapter 3's report
        # — the field was written as an empty list with no indication anything had gone
        # wrong), fall back to the curated timeline the World+Timeline stage already built.
        if not key_events:
            key_events = self._key_events_from_timeline(state, delta)
            if key_events:
                logger.info("LLM critique returned no key_events; derived them from the curated timeline.")

        # Second LLM pass: decide what actually matters. The critique above notices things;
        # this ranks the rule-based signals and the critique's own findings together,
        # writes a developmental editor's letter, and is the layer that turns a flat list
        # of detector output into a review a human would recognize as one.
        synthesis = {}
        try:
            synthesis = self._run_synthesis(state, delta, signals, llm_findings, key_events, raw_text=raw_text)
        except Exception as e:
            logger.error(f"Failed to run LLM synthesis pass: {e}")

        from datetime import datetime
        report = {
            "metadata": {
                "chapter": delta.chapter_number if delta else state.last_processed_chapter,
                "generated_at": datetime.now().isoformat(),
                "inspector_count": len(self.inspectors),
                "llm_provider": self._llm.provider_name,
                "raw_finding_count": rule_based_count,
                "total_finding_count": len(norm),
                "signal_group_count": len(signals),
                "synthesized": bool(synthesis.get("top_findings") or synthesis.get("editorial_letter")),
            },
            # The headline output: a prose developmental note, and the handful of issues
            # worth a writer's attention, ranked. Empty when no LLM was reachable — in
            # which case `signals` below is the whole review.
            "editorial_letter": synthesis.get("editorial_letter", ""),
            "strengths": synthesis.get("strengths", []),
            "top_findings": synthesis.get("top_findings", []),
            # Human-readable story beats for the chapter — from the LLM critique, or the
            # curated timeline as a fallback. Never the raw subject-verb-object triples.
            "key_events": synthesis.get("key_events") or key_events,
            # Deduplicated rule-based signals, each with a count and exemplars. This is
            # what the synthesis pass reasoned over, exposed so a human can audit it.
            "signals": signals,
            # Every raw finding, kept for back-compatibility and drill-down.
            "findings": norm,
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

    # Chapter text is by far the largest and most compressible part of both editorial
    # prompts, so it is what gets cut when a backend rejects the request size.
    _TRUNCATED_RAW_TEXT_CHARS = 3500

    def _chat_with_size_retry(self, messages: List[dict], raw_text: str, purpose: str) -> str:
        """Send an editorial prompt, retrying with less chapter text if it is too large.

        Providers with a per-minute token budget (Groq's free tier permits 8,000) reject
        oversized requests outright with HTTP 413, and no amount of retrying the same
        prompt helps. Without this, a long chapter simply produced no editorial letter --
        the most valuable output in the report -- and the only trace was a logged error.
        """
        from src.utils.llm_provider import RequestTooLargeError

        try:
            return self._llm.chat(messages, response_format={"type": "json_object"})
        except RequestTooLargeError as e:
            if not raw_text or len(raw_text) <= self._TRUNCATED_RAW_TEXT_CHARS:
                raise
            logger.warning(
                f"{purpose} prompt exceeded the backend's token allowance ({e}). "
                f"Retrying with the chapter text truncated to "
                f"{self._TRUNCATED_RAW_TEXT_CHARS} chars."
            )

        truncated = (
            raw_text[: self._TRUNCATED_RAW_TEXT_CHARS]
            + "\n[... chapter text truncated to fit the model's token budget ...]"
        )
        shrunk = []
        for message in messages:
            content = message.get("content", "")
            shrunk.append({**message, "content": content.replace(raw_text, truncated)})
        return self._llm.chat(shrunk, response_format={"type": "json_object"})

    def _key_events_from_timeline(self, state: NarrativeState, delta: StateDelta | None) -> List[str]:
        """Derive reader-facing key events for this chapter from the curated timeline.

        Fallback for when the LLM critique call fails or returns no key_events. Reads only
        `kind == "narrative"` beats (plus deaths, which are structural but genuinely
        story-level), ordered by significance, so it never degenerates into the raw
        subject-verb-object triples that now live in state.raw_relations.
        """
        chapter = delta.chapter_number if delta else state.last_processed_chapter

        candidates = []
        for event in getattr(state, "timeline", []) or []:
            if not isinstance(event, dict) or event.get("chapter") != chapter:
                continue
            kind = event.get("kind", "narrative")
            if kind == "structural" and not event.get("reader_facing"):
                continue
            summary = (event.get("summary") or "").strip()
            if not summary:
                subject = event.get("subject") or ""
                predicate = event.get("predicate") or ""
                obj = event.get("object") or ""
                summary = f"{subject} {predicate} {obj}".strip()
            if not summary:
                continue
            try:
                significance = float(event.get("significance") or 0.5)
            except (TypeError, ValueError):
                significance = 0.5
            candidates.append((significance, summary))

        candidates.sort(key=lambda pair: -pair[0])
        return [summary for _, summary in candidates[:8]]

    def _run_synthesis(
        self,
        state: NarrativeState,
        delta: StateDelta | None,
        signals: List[dict],
        llm_findings: List[dict],
        key_events: List[str],
        raw_text: str = "",
    ) -> dict:
        """Rank everything the review found and write a developmental editor's letter.

        This is the layer the previous design was missing entirely. Before it, the report
        was a flat concatenation: nine inspectors' per-entity findings, plus whatever the
        single critique call produced, in no particular order and with no relationship to
        each other. Nothing decided which of 81 findings a writer should act on, nothing
        noticed when 50 of them were the same detector firing repeatedly, and nothing
        connected a rule-based signal ("object relocated with no one present") to the
        LLM's own reading of the chapter.

        The rule-based signals arrive pre-grouped (src/review/signal_triage.py), so this
        prompt sees ~17 distinct observations rather than 81 rows, most of them duplicates.
        """
        if not self._llm.is_available:
            logger.info("No LLM provider available. Skipping synthesis pass; report will be signals-only.")
            return {}

        chapter = delta.chapter_number if delta else state.last_processed_chapter

        signal_block = render_signals_for_prompt(signals)

        critique_block = "(the critique pass produced no findings)"
        if llm_findings:
            critique_lines = []
            for finding in llm_findings[:15]:
                critique_lines.append(
                    f"- [{finding.get('severity', 'note')}] {finding.get('category', 'general')} - "
                    f"{finding.get('title', 'untitled')}: {finding.get('description', '')}"
                )
            critique_block = "\n".join(critique_lines)

        events_block = "\n".join(f"- {event}" for event in key_events) if key_events else "(none identified)"

        prompt = (
            f"You are the senior developmental editor on this manuscript, writing up "
            f"Chapter {chapter}.\n\n"
            f"--- Chapter {chapter} text ---\n{raw_text if raw_text else '(not supplied)'}\n\n"
            f"--- What this chapter appears to do (extracted story beats) ---\n{events_block}\n\n"
            f"--- Automated rule-based signals ---\n"
            f"These come from mechanical detectors run over the story's structured state. They "
            f"are grouped: 'fired 50x' means one rule matched fifty entities, which is usually "
            f"ONE issue (often a miscalibrated detector), never fifty. Treat them as leads to "
            f"verify against the chapter text, not as conclusions. Discard any that the text "
            f"does not actually support.\n{signal_block}\n\n"
            f"--- A first-pass reading of the chapter ---\n{critique_block}\n\n"
            f"--- Your task ---\n"
            f"Write the editorial assessment. Be specific to THIS chapter and quote or "
            f"reference actual moments in it. A note that would apply to any chapter of any "
            f"book is worthless - do not write 'some sentences could be revised for better "
            f"clarity' or 'consider adding more context'. Say which sentence, and what is "
            f"wrong with it.\n\n"
            f"Return between 3 and 7 top_findings. Fewer is better than padding. Rank them by "
            f"what you would actually raise with the author first. Merge duplicates: if a "
            f"rule-based signal and the first-pass reading describe the same problem, that is "
            f"ONE finding. Drop signals you judge to be detector noise, and say so in the "
            f"letter if a detector is clearly misfiring.\n\n"
            f"Format your response EXACTLY as a single JSON object, no markdown fences:\n"
            f"{{\n"
            f'  "editorial_letter": "2-5 paragraphs, addressed to the author. What this '
            f"chapter is doing, whether it works, and what you would change. Written as prose, "
            f'not a bulleted list.",\n'
            f'  "strengths": ["1-3 specific things this chapter does well, each referencing '
            f'an actual moment in it"],\n'
            f'  "top_findings": [\n'
            f"    {{\n"
            f'      "severity": "error|warning|suggestion|note",\n'
            f'      "category": "consistency|pacing|character|arc|theme|voice|structure",\n'
            f'      "title": "Short, concrete headline naming the actual problem",\n'
            f'      "description": "What is wrong, anchored to specific text or state",\n'
            f'      "why_it_matters": "The consequence for the reader if left as-is",\n'
            f'      "recommendation": "A concrete change the author could make",\n'
            f'      "related_entities": ["character or object ids"],\n'
            f'      "subsumes": ["titles of the rule-based signals this finding covers"],\n'
            f'      "confidence": 0.0\n'
            f"    }}\n"
            f"  ],\n"
            f'  "key_events": ["3-8 plain-English story beats for this chapter, corrected '
            f'if the extracted list above got them wrong"]\n'
            f"}}\n"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior developmental editor. You are blunt, specific, and you "
                    "never pad. You respond strictly as a single JSON object with the requested "
                    "fields and nothing else - no markdown fences, no preamble."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        logger.info(f"Running LLM editorial synthesis via {self._llm.provider_name} (model: {self._llm.model})...")
        raw_output = self._chat_with_size_retry(messages, raw_text, "Synthesis")
        return self._parse_synthesis(raw_output, chapter)

    def _parse_synthesis(self, raw_output: str, chapter_num: int) -> dict:
        """Parse the synthesis pass's JSON object, tolerating conversational wrapping."""
        import re

        cleaned = (raw_output or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        parsed = None
        try:
            parsed = json.loads(cleaned)
        except Exception:
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                except Exception:
                    parsed = None

        if not isinstance(parsed, dict):
            logger.warning("Synthesis pass response did not parse as a JSON object; ignoring it.")
            return {}

        top_findings = []
        for rank, finding in enumerate(parsed.get("top_findings") or [], start=1):
            if not isinstance(finding, dict):
                continue
            finding["rank"] = rank
            finding["chapter"] = chapter_num
            finding.setdefault("related_entities", [])
            finding.setdefault("subsumes", [])
            finding.setdefault("evidence_ids", [])
            top_findings.append(finding)

        def _string_list(key: str) -> List[str]:
            value = parsed.get(key)
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()]

        return {
            "editorial_letter": str(parsed.get("editorial_letter") or "").strip(),
            "strengths": _string_list("strengths"),
            "top_findings": top_findings,
            "key_events": _string_list("key_events"),
        }

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
            f"Critique the current chapter against the story memory above, reasoning across the "
            f"accumulated chapter summaries and recent timeline — not just this chapter in "
            f"isolation. Specifically:\n"
            f"1. **Thematic Pacing Drift**: Is the chapter's pacing consistent with the arc "
            f"established across prior chapters, or does it introduce sudden shifts, drag, or "
            f"rushed scenes?\n"
            f"2. **Stylistic Variance**: Is there a noticeable stylistic, voice, or tone shift in "
            f"this chapter compared to the established narrative voice?\n"
            f"3. **Mystery/Conflict cross-referencing**: Cross-reference newly emerged conflict "
            f"events against open mysteries (contradiction events, inventory dual-ownership, "
            f"physical description mismatches) to flag genuine contradictions.\n\n"
            f"RULES FOR EVERY FINDING — these exist because earlier passes returned unusable "
            f"filler:\n"
            f"- Anchor each finding to a specific moment. Name the sentence, character, or object. "
            f"A finding that could be pasted into a review of any chapter of any novel is worse "
            f"than no finding.\n"
            f"- BANNED phrasings: 'generally well-written', 'some sentences could be revised', "
            f"'consider adding more context', 'might feel a bit rushed to some readers', "
            f"'consider reviewing for minor adjustments'. If your finding reduces to one of "
            f"these, delete it.\n"
            f"- Do not hedge a finding into meaninglessness. If the chapter is fine on one of the "
            f"three axes above, return NO finding for that axis rather than a neutral one. An "
            f"empty findings list is a valid and useful answer.\n"
            f"- Return at most 6 findings.\n\n"
            f"Also summarize the chapter's key events: 3-8 short, plain-English sentences "
            f"describing what actually happened that a reader would care about (plot-significant "
            f"actions, revelations, decisions, arrivals/departures) — not every sentence-level "
            f"action, and not scene-setting. This field is required; never return it empty when "
            f"the chapter contains any events at all.\n\n"
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
            raw_output = self._chat_with_size_retry(messages, raw_text, "Critique")
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

