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

import concurrent.futures
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
        """Run stages A/B/C in parallel, then D, and return a merged delta dict."""
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_a = executor.submit(self._fetch_json, system_content, prompt_a)
            future_b = executor.submit(self._fetch_json, system_content, prompt_b)
            future_c = executor.submit(self._fetch_json, system_content, prompt_c)
            data_a = self._safe_result(future_a, "character_relationship")
            data_b = self._safe_result(future_b, "world_timeline_scene")
            data_c = self._safe_result(future_c, "thematic")

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
            data_d = self._fetch_json(system_content, prompt_d)
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

    def _fetch_json(self, system_content: str, prompt: str) -> Dict[str, Any]:
        """Call the configured LLM backend and parse its JSON response.

        Instantiates its own LLMProvider (thread-safe: stages A/B/C run concurrently).
        Any failure — no backend available, HTTP error, malformed JSON — degrades to
        an empty dict rather than raising, so one stage's failure never blocks the others.
        """
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
        except Exception as e:
            logger.error(f"LLM extraction stage failed: {e}")
            return {}

    def _safe_result(self, future: "concurrent.futures.Future", stage_name: str) -> Dict[str, Any]:
        try:
            return future.result(timeout=300)
        except Exception as e:
            logger.warning(f"LLM extraction stage '{stage_name}' timed out or failed: {e}")
            return {}
