"""
LLM Extraction Engine — Specialized, context-aware LLM reasoning stages.

The engine owns structured knowledge; the LLM owns interpretation. This module
is where that interpretation happens, split into focused stages instead of one
prompt trying to do everything:

  Stage A (character_relationship): character state changes, relationship mutations.
  Stage B (world_timeline_scene):   world/object state, chronological events.
  Stage C (thematic):               themes, motifs, promises, threats.
  Stage D (consistency_checker):    cross-references A/B/C's own proposals against
                                     the existing NarrativeState to flag contradictions —
                                     runs AFTER A/B/C, not in place of reading them.

Every stage receives: the deterministic evidence already extracted by the NLP
pipeline (GLiNER entities, FastCoref clusters, dependency-parsed relations,
dialogue) and the ContextRetriever-hydrated relevant slice of story memory. No
stage ever reasons over raw chapter text alone — it never has to rediscover
what deterministic NLP already found.

Everything returned here is a PROPOSAL, not a state mutation. Nothing here
writes to NarrativeState — that happens in StateEngine, which is responsible
for actually applying (and, from Phase 5 onward, validating) these proposals.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger("NarrativeEngine.Pipeline.LLMExtraction")


_SYSTEM_PREAMBLE = (
    "You are a professional developmental editor. You output strictly a single JSON "
    "object matching the requested schema and nothing else. Never include explanations, "
    "intro/outro, or markdown backticks. Output pure JSON."
)


class LLMExtractionEngine:
    """Runs the specialized LLM reasoning stages for one chapter."""

    def __init__(self, config=None):
        self._config = config

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def extract(self, chapter_num: int, cleaned_text: str, chapter_data, context_block: str) -> Dict[str, Any]:
        """Run stages A/B/C sequentially, then D, and return a merged delta dict.

        Sequential rather than concurrent on purpose -- see the comment at the call site.
        """
        evidence_block = self._build_evidence_block(chapter_data)
        system_content = (
            f"{_SYSTEM_PREAMBLE}\n\n"
            f"{context_block or ''}\n\n"
            f"{evidence_block}\n\n"
            "Contrast the raw text of the incoming chapter against the provided "
            "<StoryContext> and <DeterministicEvidence> to ground your answer in what is "
            "already known, rather than re-discovering it. Only infer what the evidence "
            "and text actually support."
        )

        prompt_a = self._build_character_relationship_prompt(chapter_num, cleaned_text)
        prompt_b = self._build_world_timeline_prompt(chapter_num, cleaned_text)
        prompt_c = self._build_thematic_prompt(chapter_num, cleaned_text)

        # Stages run SEQUENTIALLY, not concurrently. They were parallel (a
        # ThreadPoolExecutor with three workers) which is the right shape for a
        # latency-bound workload and the wrong one for a token-bound one: three ~6k-token
        # prompts issued at once consume ~18k tokens instantaneously, and a provider with
        # a per-minute token budget (Groq's free tier allows 8,000 TPM) rejects most of
        # them outright. Every stage then failed and the chapter fell back to
        # deterministic-only extraction. Sequential costs wall-clock time on a batch job
        # that is already minutes per chapter, and actually completes.
        data_a = self._run_stage("character_relationship", system_content, prompt_a)
        data_b = self._run_stage("world_timeline_scene", system_content, prompt_b)
        data_c = self._run_stage("thematic", system_content, prompt_c)

        delta: Dict[str, Any] = {
            "chapter_summary": data_a.get("chapter_summary", ""),
            "character_updates": data_a.get("character_updates", []),
            "relationship_mutations": data_a.get("relationship_mutations", []),
            "world_updates": data_b.get("world_updates", []),
            "timeline_events": data_b.get("timeline_events", []),
            "promises_delta": data_c.get("promises_delta", []),
            "threats_delta": data_c.get("threats_delta", []),
            "themes_delta": data_c.get("themes_delta", []),
            "motifs_delta": data_c.get("motifs_delta", []),
            "structural_mysteries": [],
        }

        has_any_proposal = any(
            isinstance(delta.get(k), list) and len(delta[k]) > 0
            for k in ("character_updates", "relationship_mutations", "world_updates", "timeline_events")
        )
        if has_any_proposal:
            prompt_d = self._build_consistency_prompt(chapter_num, cleaned_text, data_a, data_b, data_c)
            data_d = self._run_stage("consistency_checker", system_content, prompt_d)
            delta["structural_mysteries"] = data_d.get("structural_mysteries", [])
        else:
            logger.info(f"Chapter {chapter_num}: no proposals from stages A-C; skipping consistency checker call.")

        return delta

    # ------------------------------------------------------------------
    # Deterministic evidence grounding
    # ------------------------------------------------------------------

    def _build_evidence_block(self, chapter_data) -> str:
        """Summarize deterministic NLP evidence already extracted for this chapter.

        This is what lets the LLM interpret rather than rediscover: entities,
        coreference clusters, dependency-parsed relations, and dialogue
        attributions are all already known before any LLM call is made.
        """
        entities_by_label: Dict[str, List[str]] = {}
        for e in getattr(chapter_data, "entities", []):
            entities_by_label.setdefault(e.label, []).append(e.text)

        entity_lines = []
        for label, texts in entities_by_label.items():
            unique_texts = sorted(set(texts))[:20]
            entity_lines.append(f"    <Entities type=\"{label}\">{', '.join(unique_texts)}</Entities>")

        coref_lines = []
        for cluster in getattr(chapter_data, "coreferences", [])[:15]:
            mentions = ", ".join(sorted(set(cluster.mentions))[:8])
            coref_lines.append(f"    <Cluster canonical=\"{cluster.canonical_mention}\">{mentions}</Cluster>")

        relation_lines = []
        for rel in getattr(chapter_data, "relations", [])[:25]:
            relation_lines.append(f"    <Relation>{rel.subject} {rel.predicate} {rel.object}</Relation>")

        dialogue_lines = []
        for d in getattr(chapter_data, "dialogues", [])[:15]:
            snippet = d.text[:120].replace("\n", " ")
            dialogue_lines.append(f"    <Line speaker=\"{d.speaker}\">{snippet}</Line>")

        return (
            "<DeterministicEvidence note=\"Already extracted by GLiNER/FastCoref/dependency-parse/"
            "dialogue-extraction. Reuse these surface forms and ids where they refer to the same "
            "thing rather than inventing new ones.\">\n"
            "  <Entities>\n" + ("\n".join(entity_lines) if entity_lines else "    (none)") + "\n  </Entities>\n"
            "  <CoreferenceClusters>\n" + ("\n".join(coref_lines) if coref_lines else "    (none)") + "\n  </CoreferenceClusters>\n"
            "  <DependencyRelations>\n" + ("\n".join(relation_lines) if relation_lines else "    (none)") + "\n  </DependencyRelations>\n"
            "  <Dialogue>\n" + ("\n".join(dialogue_lines) if dialogue_lines else "    (none)") + "\n  </Dialogue>\n"
            "</DeterministicEvidence>"
        )

    # ------------------------------------------------------------------
    # Stage prompts
    # ------------------------------------------------------------------

    def _build_character_relationship_prompt(self, chapter_num: int, cleaned_text: str) -> str:
        return (
            f"Analyze Chapter {chapter_num} raw text below.\n\n"
            f"--- Chapter {chapter_num} Raw Text ---\n{cleaned_text}\n\n"
            f"--- Output Requirements ---\n"
            f"Focus ONLY on characters and their relationships. Return JSON matching:\n"
            f"{{\n"
            f"  \"chapter_summary\": \"A concise paragraph summarizing the events of this chapter\",\n"
            f"  \"character_updates\": [\n"
            f"    {{\n"
            f"      \"character_id\": \"id\",\n"
            f"      \"canonical_name\": \"Name\",\n"
            f"      \"aliases_discovered\": [\"aliases\"],\n"
            f"      \"traits_mutated\": {{ \"trait\": {{\"value\": \"val\", \"confidence\": 1.0, \"reasoning\": \"...\"}} }},\n"
            f"      \"goals_updated\": [\"goals\"],\n"
            f"      \"fears_updated\": [\"fears\"],\n"
            f"      \"inventory_delta\": {{\n"
            f"        \"added\": [{{ \"item_id\": \"id\", \"causal_actor\": \"character_id or UNKNOWN_ACTOR\", \"timestamp_inferred\": \"time\" }}],\n"
            f"        \"removed\": [{{ \"item_id\": \"id\", \"causal_actor\": \"character_id or UNKNOWN_ACTOR\", \"timestamp_inferred\": \"time\" }}]\n"
            f"      }},\n"
            f"      \"current_location_id\": \"location_id\",\n"
            f"      \"timestamp_inferred\": \"time\"\n"
            f"    }}\n"
            f"  ],\n"
            f"  \"relationship_mutations\": [\n"
            f"    {{\n"
            f"      \"party_a\": \"id1\",\n"
            f"      \"party_b\": \"id2\",\n"
            f"      \"stance\": \"ROMANTIC|ENMITY|ALLIANCE|NEUTRAL\",\n"
            f"      \"reasoning\": \"...\"\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
        )

    def _build_world_timeline_prompt(self, chapter_num: int, cleaned_text: str) -> str:
        return (
            f"Analyze Chapter {chapter_num} raw text below.\n\n"
            f"--- Chapter {chapter_num} Raw Text ---\n{cleaned_text}\n\n"
            f"--- Output Requirements ---\n"
            f"Focus ONLY on world state (objects/locations) and the chronological sequence of "
            f"events. Return JSON matching:\n"
            f"{{\n"
            f"  \"world_updates\": [\n"
            f"    {{\n"
            f"      \"item_id\": \"item_id\",\n"
            f"      \"type\": \"object\",\n"
            f"      \"current_location_id\": \"location\",\n"
            f"      \"owner_character_id\": null,\n"
            f"      \"causal_actor\": \"character_id or UNKNOWN_ACTOR\",\n"
            f"      \"timestamp_inferred\": \"time\"\n"
            f"    }}\n"
            f"  ],\n"
            f"  \"timeline_events\": [\n"
            f"    {{\n"
            f"      \"subject\": \"character_id or item_id\",\n"
            f"      \"predicate\": \"short verb phrase, e.g. 'dies', 'moves_to', 'discovers'\",\n"
            f"      \"object\": \"target of the action\",\n"
            f"      \"time\": \"time or ordering hint mentioned in the text, or null\",\n"
            f"      \"causes\": \"id of an earlier event in this same list this one follows from, or null\",\n"
            f"      \"confidence\": 1.0\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"Only include timeline_events for concrete plot-relevant actions actually described "
            f"in the text — not scene-setting description.\n"
        )

    def _build_thematic_prompt(self, chapter_num: int, cleaned_text: str) -> str:
        return (
            f"Analyze Chapter {chapter_num} raw text below.\n\n"
            f"--- Chapter {chapter_num} Raw Text ---\n{cleaned_text}\n\n"
            f"--- Output Requirements ---\n"
            f"Focus ONLY on promises, threats, themes, and motifs. Return JSON matching:\n"
            f"{{\n"
            f"  \"promises_delta\": [\n"
            f"    {{\n"
            f"      \"promise_id\": \"id\",\n"
            f"      \"text\": \"text\",\n"
            f"      \"speaker_id\": \"id\",\n"
            f"      \"listener_id\": \"id\",\n"
            f"      \"status\": \"OPEN|FULFILLED|BROKEN\",\n"
            f"      \"reasoning\": \"...\"\n"
            f"    }}\n"
            f"  ],\n"
            f"  \"threats_delta\": [\n"
            f"    {{\n"
            f"      \"threat_id\": \"id\",\n"
            f"      \"text\": \"text\",\n"
            f"      \"target_id\": \"id\",\n"
            f"      \"source_id\": \"id\",\n"
            f"      \"status\": \"ACTIVE|RESOLVED\",\n"
            f"      \"reasoning\": \"...\"\n"
            f"    }}\n"
            f"  ],\n"
            f"  \"themes_delta\": [\n"
            f"    {{ \"theme_id\": \"id\", \"description\": \"description\", \"reasoning\": \"...\" }}\n"
            f"  ],\n"
            f"  \"motifs_delta\": [\n"
            f"    {{ \"motif_id\": \"id\", \"description\": \"description\", \"reasoning\": \"...\" }}\n"
            f"  ]\n"
            f"}}\n"
        )

    def _build_consistency_prompt(
        self,
        chapter_num: int,
        cleaned_text: str,
        data_a: Dict[str, Any],
        data_b: Dict[str, Any],
        data_c: Dict[str, Any],
    ) -> str:
        proposals = {
            "character_updates": data_a.get("character_updates", []),
            "relationship_mutations": data_a.get("relationship_mutations", []),
            "world_updates": data_b.get("world_updates", []),
            "timeline_events": data_b.get("timeline_events", []),
            "promises_delta": data_c.get("promises_delta", []),
            "threats_delta": data_c.get("threats_delta", []),
        }
        return (
            f"You are checking PROPOSED updates for Chapter {chapter_num} against the existing "
            f"<StoryContext> and <DeterministicEvidence> already provided, and against each other.\n\n"
            f"--- Chapter {chapter_num} Raw Text (for reference only) ---\n{cleaned_text}\n\n"
            f"--- Proposed Updates (NOT yet applied — your job is to sanity-check them) ---\n"
            f"{json.dumps(proposals, indent=2)}\n\n"
            f"--- Output Requirements ---\n"
            f"Identify contradictions between these proposals and the existing story state, or "
            f"between the proposals themselves — e.g. a character in two places at once, an object "
            f"changing location with no one who could have moved it, a timeline event that "
            f"contradicts an earlier one, a character acting on knowledge they have no way of "
            f"having, or a proposal referencing an entity with no support in the evidence provided. "
            f"Return JSON matching:\n"
            f"{{\n"
            f"  \"structural_mysteries\": [\n"
            f"    {{\n"
            f"      \"issue_type\": \"INVENTORY_TELEPORTATION|EMOTIONAL_INVERSION|TIMELINE_GAP|"
            f"LOCATION_CONTRADICTION|KNOWLEDGE_LEAK|UNSUPPORTED_ENTITY\",\n"
            f"      \"severity\": \"CRITICAL|WARNING|NOTE\",\n"
            f"      \"description\": \"...\",\n"
            f"      \"related_entities\": [\"ids\"]\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"If nothing is actually contradictory, return an empty list. Do not invent issues.\n"
        )

    # ------------------------------------------------------------------
    # LLM plumbing
    # ------------------------------------------------------------------

    def _run_stage(self, stage_name: str, system_content: str, prompt: str) -> Dict[str, Any]:
        """Run one extraction stage, shrinking the request if the backend rejects its size.

        A `RequestTooLargeError` is not a failure of the stage, it is a statement that this
        particular prompt does not fit the backend's token allowance — so the stage is
        retried with the most compressible part removed rather than abandoned. The
        `<StoryContext>` block goes first (it is accumulated background, and the chapter
        text plus deterministic evidence are what the stage is actually reasoning about);
        if that is still too large, the chapter text is truncated.
        """
        from src.utils.llm_provider import RequestTooLargeError

        attempts = [
            ("full", system_content, prompt),
            ("context-trimmed", self._trim_context_block(system_content), prompt),
            (
                "context-trimmed + text-truncated",
                self._trim_context_block(system_content),
                self._truncate_chapter_text(prompt),
            ),
        ]

        for label, sys_content, user_prompt in attempts:
            try:
                return self._fetch_json(sys_content, user_prompt, raise_too_large=True)
            except RequestTooLargeError as e:
                logger.warning(
                    f"Stage '{stage_name}' prompt too large for the backend ({label}): {e}. "
                    f"Retrying with a smaller request."
                )
            except Exception as e:
                logger.error(f"LLM extraction stage '{stage_name}' failed: {e}")
                return {}

        logger.error(
            f"LLM extraction stage '{stage_name}' could not be made to fit the backend's "
            f"token allowance even after trimming; skipping it."
        )
        return {}

    @staticmethod
    def _trim_context_block(system_content: str) -> str:
        """Drop the accumulated <StoryContext> block, keeping the evidence and instructions."""
        start = system_content.find("<StoryContext")
        if start == -1:
            return system_content
        end = system_content.find("</StoryContext>")
        if end == -1:
            return system_content
        end += len("</StoryContext>")
        return (
            system_content[:start]
            + "(prior story context omitted to fit the model's token budget)"
            + system_content[end:]
        )

    @staticmethod
    def _truncate_chapter_text(prompt: str, keep_chars: int = 4000) -> str:
        """Keep only the opening of the chapter text embedded in a stage prompt."""
        marker = "--- Output Requirements ---"
        split_at = prompt.find(marker)
        if split_at == -1 or split_at <= keep_chars:
            return prompt
        return (
            prompt[:keep_chars]
            + "\n[... chapter text truncated to fit the model's token budget ...]\n\n"
            + prompt[split_at:]
        )

    def _fetch_json(self, system_content: str, prompt: str, raise_too_large: bool = False) -> Dict[str, Any]:
        """Call the configured LLM backend and parse its JSON response.

        Instantiates its own LLMProvider per call. (Stages used to run concurrently and
        needed that isolation; they are sequential now, but a fresh provider also picks up
        any backend retirement recorded by an earlier stage, which is class-level state.)
        Any failure — no backend available, HTTP error, malformed JSON — degrades to
        an empty dict rather than raising, so one stage's failure never blocks the others.
        """
        from src.utils.llm_provider import RequestTooLargeError

        try:
            from src.utils.llm_provider import LLMProvider
            llm = LLMProvider(self._config)
            if not llm.is_available:
                return {}
            resp = llm.chat(
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            cleaned = resp.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            return json.loads(cleaned)
        except RequestTooLargeError:
            # Surfaced to _run_stage, which retries with a smaller prompt. Swallowing it
            # here would silently drop the stage on a request that a trim would have fixed.
            if raise_too_large:
                raise
            return {}
        except Exception as e:
            logger.error(f"LLM extraction stage failed: {e}")
            return {}
