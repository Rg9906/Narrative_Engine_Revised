"""
State Engine — Unified Hybrid LLM State Application and Atomic Persistence.

Linearly applies the structured JSON mutations, updates, and contradictions
from the Gemini API to the NarrativeState.
"""

from __future__ import annotations

import logging
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.models.state import (
    ChapterData,
    Evidence,
    EvidenceType,
    NarrativeElementType,
    NarrativeState,
    StateChange,
    StateChangeType,
    StateDelta,
    StateSnapshot,
    StateEntry,
)
from src.engines.validation_engine import ValidationEngine
from src.utils import stable_hash

logger = logging.getLogger("NarrativeEngine.Engines.StateEngine")


class StateEngine:
    """
    Unified LLM State Engine.

    Parses LLM sensory delta outputs and applies updates to the NarrativeState
    with defensive guardrails and atomic persistence.
    """

    def __init__(self, config=None):
        self._config = config
        self._validator = ValidationEngine(config)

    def process_chapter(
        self,
        chapter_data: ChapterData,
        current_state: NarrativeState,
    ) -> StateDelta:
        """
        Process the LLM-generated sensory delta and update the NarrativeState.
        """
        chapter_num = chapter_data.chapter_number
        delta = StateDelta(chapter_number=chapter_num)
        
        llm_delta = getattr(chapter_data, "llm_delta", {})
        has_updates = any(
            isinstance(llm_delta.get(k), list) and len(llm_delta[k]) > 0
            for k in ("character_updates", "relationship_mutations", "promises_delta", "world_updates", "structural_mysteries")
        )

        # --- PASS 1: Deterministic memory update — ALWAYS runs first. ---
        # GLiNER/FastCoref/dialogue evidence already attached to chapter_data seeds candidate
        # characters, relationships, world objects, timeline entries, themes, promises, mysteries
        # and style stats via the src/memory/*.py update_from_chapter() chain. Any LLM-authored
        # delta (Pass 2 below) is layered on top of this deterministic baseline as a refinement,
        # never as a replacement for it.
        logger.info(f"Running deterministic memory update pass for chapter {chapter_num}.")
        from src.memory.character_memory import CharacterMemory
        from src.memory.relationship_memory import RelationshipMemory
        from src.memory.world_memory import WorldMemory
        from src.memory.timeline_memory import TimelineMemory
        from src.memory.theme_memory import ThemeMemory
        from src.memory.promise_memory import PromiseMemory
        from src.memory.mystery_memory import MysteryMemory
        from src.memory.style_memory import StyleMemory
        from src.utils.llm_provider import LLMProvider

        # Passed through to CharacterMemory as a last-resort coreference disambiguation
        # fallback (see CharacterMemory._disambiguate_cluster_with_llm) — only used when
        # a FastCoref cluster's canonical mention doesn't match any known character by
        # name. Cheap to construct (backend auto-detection only, no model load); degrades
        # to a no-op automatically when no LLM backend is available, same as every other
        # LLM integration point in this codebase.
        character_memory = CharacterMemory(
            existing_entries=current_state.characters,
            llm_provider=LLMProvider(self._config),
        )
        character_changes = character_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(character_changes)

        advanced_character_changes = character_memory.extract_advanced_attributes(chapter_data, chapter_num)
        delta.changes.extend(advanced_character_changes)

        relationship_memory = RelationshipMemory()
        relationship_memory.load(current_state.relationships)
        # Pass character_memory.entries (just updated above), not current_state.characters
        # (which still reflects the state BEFORE this chapter's characters were added) — a
        # character introduced for the first time this chapter must still be recognizable
        # as a character when RelationshipMemory checks relation participants below.
        relationship_changes = relationship_memory.update_from_chapter(
            chapter_data, chapter_num, existing_characters=character_memory.entries
        )
        delta.changes.extend(relationship_changes)

        world_memory = WorldMemory()
        world_memory.load(current_state.world)
        world_changes = world_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(world_changes)

        timeline_memory = TimelineMemory()
        timeline_changes = timeline_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(timeline_changes)

        theme_memory = ThemeMemory(existing_entries=current_state.themes)
        theme_changes = theme_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(theme_changes)

        promise_memory = PromiseMemory(existing_entries=current_state.promises)
        promise_changes = promise_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(promise_changes)

        mystery_memory = MysteryMemory(existing_entries=current_state.mysteries)
        mystery_changes = mystery_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(mystery_changes)

        style_memory = StyleMemory(existing_entries=current_state.style)
        style_changes = style_memory.update_from_chapter(chapter_data, chapter_num)
        delta.changes.extend(style_changes)

        # Persist deterministic pass back onto current_state
        current_state.characters = character_memory.entries
        current_state.relationships = relationship_memory.entries
        current_state.world = world_memory.entries
        current_state.themes = theme_memory.entries
        current_state.promises = promise_memory.entries
        current_state.mysteries = mystery_memory.entries
        current_state.style = style_memory.entries

        # Append timeline events from deterministic relation evidence
        for rel in getattr(chapter_data, "relations", []):
            event = {
                "chapter": chapter_num,
                "subject": getattr(rel, "subject", None),
                "predicate": getattr(rel, "predicate", None),
                "object": getattr(rel, "object", None),
            }
            current_state.timeline.append(event)

        if not current_state.timeline:
            current_state.timeline.append({
                "chapter": chapter_num,
                "subject": "System",
                "predicate": "initiated",
                "object": "Chapter"
            })

        # --- PASS 2: LLM-authored delta refinement — only if the pipeline produced one. ---
        if not llm_delta or not has_updates:
            logger.info(f"No LLM delta for chapter {chapter_num}; deterministic pass is the final result.")
            return delta

        logger.info(f"Layering LLM-authored delta refinement onto deterministic baseline for chapter {chapter_num}.")

        delta.rejected_proposals = []

        # Entities the consistency-checker stage (Stage D of LLMExtractionEngine) already flagged
        # this chapter — fed into ValidationEngine as a live signal, not just a display-only note.
        flagged_entity_ids = set()
        for mystery in llm_delta.get("structural_mysteries", []):
            for ent in mystery.get("related_entities", []) or []:
                if isinstance(ent, str):
                    flagged_entity_ids.add(ent.strip().lower())

        def log_contradiction_mystery(target_id: str, description: str) -> None:
            # stable_hash (not builtin hash()) -- Python's hash() is randomized per-process
            # (PYTHONHASHSEED) unless explicitly pinned, so re-running the pipeline over the
            # same chapter would generate a different id each time and duplicate this mystery
            # instead of updating it. Caught by a self-review pass.
            conflict_id = f"conflict_{target_id}_{chapter_num}_{stable_hash(description)[:4]}"
            conflict_entry = current_state.mysteries.setdefault(conflict_id, {})

            def _set(key: str, val: Any) -> None:
                if key not in conflict_entry:
                    conflict_entry[key] = StateEntry(key=key, element_type=NarrativeElementType.MYSTERY)
                conflict_entry[key].update(StateSnapshot(value=val, chapter=chapter_num, confidence=1.0, reasoning="Logged by ValidationEngine."))

            _set("mystery_text", description)
            _set("status", "unresolved")
            _set("chapter_introduced", chapter_num)
            _set("type", "conflict")
            logger.warning(f"Validation contradiction: {description}")

        # 0. Apply Chapter Summary
        summary = llm_delta.get("chapter_summary")
        if summary:
            current_state.chapter_summaries[chapter_num] = summary

        # Normalize item names. Generic regex normalization only — no manuscript-specific
        # special-casing (a prior version hardcoded "wedding ring" / "emperor's scarab" from a
        # different demo story; that's exactly the kind of story-specific logic this project
        # intentionally excludes now). Mirrors CharacterMemory._normalize_entity_id's approach.
        def normalize_item_name(item: str) -> str:
            import re
            item_clean = item.strip().lower()
            item_clean = re.sub(r"[^a-z0-9]+", "_", item_clean)
            return re.sub(r"_+", "_", item_clean).strip("_")

        # Exclusions for immovable structures (generic vocabulary, not story-specific)
        IMMOVABLE_STRUCTURES = {"fireplace", "staircase", "hearth", "floorboard", "desk", "bookshelf", "mantlepiece", "library_shelves", "shelves"}

        # 1. Apply Character Updates
        for char_update in llm_delta.get("character_updates", []):
            raw_char_id = char_update.get("character_id")
            if not raw_char_id:
                continue

            # Resolve against characters the deterministic Pass 1 (above) already seeded,
            # so the LLM's own id/casing for someone it already knows about (e.g. "Laurie")
            # doesn't create a duplicate of what Pass 1 identified as "laurie". Reuses
            # CharacterMemory's existing alias/proper-noun resolution rather than trusting
            # the LLM's raw id verbatim.
            resolution_source = char_update.get("canonical_name") or raw_char_id
            char_id = character_memory.resolve_character_id(resolution_source, current_state.characters)

            # --- Validation gate: is this proposal trustworthy enough to reach state at all? ---
            is_new_character = char_id not in current_state.characters or not current_state.characters.get(char_id)
            traits_for_confidence = char_update.get("traits_mutated", {}) or {}
            proposal_confidence = max(
                (t.get("confidence", 1.0) for t in traits_for_confidence.values()),
                default=1.0,
            )
            validation = self._validator.evaluate_entity_proposal(
                entity_id=char_id,
                mention_hint=resolution_source,
                is_new=is_new_character,
                confidence=proposal_confidence,
                chapter_data=chapter_data,
                flagged_entity_ids=flagged_entity_ids,
            )
            if not validation.accepted:
                logger.warning(f"ValidationEngine rejected character proposal '{char_id}' ({resolution_source}): {validation.reason}")
                delta.rejected_proposals.append({
                    "kind": "character_update", "entity_id": char_id,
                    "mention": resolution_source, "reason": validation.reason,
                })
                continue
            confidence_ceiling = validation.confidence if validation.confidence is not None else proposal_confidence

            char_entry = current_state.characters.setdefault(char_id, {})

            # Helper for updating a StateEntry. Every write is capped at confidence_ceiling
            # (may be downgraded by the validation gate above) and, for existing fields, passes
            # through a field-level contradiction check before being written — replacing what
            # used to be a post-hoc "revert after the fact" pass with a pre-write gate.
            def update_field(key: str, val: Any, reasoning: str, confidence: float = 1.0):
                confidence = min(confidence, confidence_ceiling)
                if key not in char_entry:
                    char_entry[key] = StateEntry(key=key, element_type=NarrativeElementType.CHARACTER)
                    change_type = StateChangeType.INTRODUCTION
                    old_val = None
                    old_conf = 0.0
                else:
                    change_type = StateChangeType.EVOLUTION
                    old_snapshot = char_entry[key].current
                    old_val = old_snapshot.value if old_snapshot else None
                    old_conf = old_snapshot.confidence if old_snapshot else 0.0

                if old_val == val:
                    return

                if change_type == StateChangeType.EVOLUTION:
                    contradiction = self._validator.check_field_contradiction(key, old_val, old_conf, val, confidence)
                    if contradiction.is_contradiction:
                        log_contradiction_mystery(char_id, contradiction.description)
                        if not contradiction.should_apply:
                            delta.changes.append(StateChange(
                                change_type=StateChangeType.CONTRADICTION,
                                target_type=NarrativeElementType.CHARACTER,
                                target_id=char_id,
                                field_key=key,
                                old_value=old_val,
                                new_value=val,
                                confidence=confidence,
                                reasoning=f"REJECTED by ValidationEngine: {contradiction.description}",
                            ))
                            return

                char_entry[key].update(StateSnapshot(
                    value=val,
                    chapter=chapter_num,
                    confidence=confidence,
                    reasoning=reasoning
                ))
                delta.changes.append(StateChange(
                    change_type=change_type,
                    target_type=NarrativeElementType.CHARACTER,
                    target_id=char_id,
                    field_key=key,
                    old_value=old_val,
                    new_value=val,
                    confidence=confidence,
                    reasoning=reasoning
                ))

            # Canonical Name
            cname = char_update.get("canonical_name")
            if cname:
                update_field("canonical_name", cname, "Canonical name set by LLM.")

            # Aliases
            aliases = char_update.get("aliases_discovered", [])
            if aliases:
                existing_aliases = char_entry.get("aliases")
                curr_aliases = list(existing_aliases.current.value) if existing_aliases and existing_aliases.current else []
                updated_aliases = list(set(curr_aliases + aliases + ([cname] if cname else [])))
                update_field("aliases", updated_aliases, "Aliases updated by LLM.")

            # Traits Mutated
            traits = char_update.get("traits_mutated", {})
            for trait_name, trait_data in traits.items():
                tval = trait_data.get("value")
                treason = trait_data.get("reasoning", "Trait mutated by LLM.")
                tconf = trait_data.get("confidence", 1.0)
                
                # Check physical trait names
                if trait_name in ("hair_color", "eye_color", "height", "build", "age"):
                    update_field(f"physical_{trait_name}", tval, treason, tconf)
                elif trait_name == "personality_traits":
                    if isinstance(tval, list):
                        update_field("personality_traits", tval, treason, tconf)
                else:
                    update_field(trait_name, tval, treason, tconf)

            # Goals
            goals = char_update.get("goals_updated")
            if goals is not None:
                update_field("goals", goals, "Goals updated by LLM.")

            # Fears
            fears = char_update.get("fears_updated")
            if fears is not None:
                update_field("fears", fears, "Fears updated by LLM.")

            # Location
            loc_id = char_update.get("current_location_id")
            if loc_id:
                update_field("location", loc_id, "Character location updated by LLM.")

            # Inventory Delta (Portable only)
            inv_delta = char_update.get("inventory_delta", {})
            existing_inv = char_entry.get("inventory")
            curr_inv = list(existing_inv.current.value) if existing_inv and existing_inv.current else []
            
            # Apply additions
            for item_obj in inv_delta.get("added", []):
                if isinstance(item_obj, dict):
                    item = item_obj.get("item_id", "")
                    causal_actor = item_obj.get("causal_actor")
                else:
                    item = str(item_obj)
                    causal_actor = None
                    
                norm_item = normalize_item_name(item)
                if not norm_item: continue
                if norm_item in IMMOVABLE_STRUCTURES:
                    logger.info(f"Defensive exclusion: barred immovable structure '{item}' from character '{char_id}' inventory.")
                    continue
                if norm_item not in curr_inv:
                    curr_inv.append(norm_item)
                    # Sync world item ownership
                    item_world = current_state.world.setdefault(norm_item, {})
                    item_world["type"] = StateEntry(key="type", element_type=NarrativeElementType.OBJECT)
                    item_world["type"].update(StateSnapshot(value="object", chapter=chapter_num))
                    item_world["owner"] = StateEntry(key="owner", element_type=NarrativeElementType.OBJECT)
                    item_world["owner"].update(StateSnapshot(value=char_id, chapter=chapter_num))
                    item_world["location"] = StateEntry(key="location", element_type=NarrativeElementType.OBJECT)
                    item_world["location"].update(StateSnapshot(value=None, chapter=chapter_num))
                    
                    if causal_actor == "UNKNOWN_ACTOR":
                        myst_id = f"mystery_ghost_inventory_{chapter_num}_{stable_hash(norm_item)[:4]}"
                        myst_entry = current_state.mysteries.setdefault(myst_id, {})
                        if "mystery_text" not in myst_entry: myst_entry["mystery_text"] = StateEntry(key="mystery_text", element_type=NarrativeElementType.MYSTERY)
                        myst_entry["mystery_text"].update(StateSnapshot(value=f"Item {norm_item} was acquired but the causal actor is unknown.", chapter=chapter_num))
                        if "status" not in myst_entry: myst_entry["status"] = StateEntry(key="status", element_type=NarrativeElementType.MYSTERY)
                        myst_entry["status"].update(StateSnapshot(value="unresolved", chapter=chapter_num))
                        if "type" not in myst_entry: myst_entry["type"] = StateEntry(key="type", element_type=NarrativeElementType.MYSTERY)
                        myst_entry["type"].update(StateSnapshot(value="ghost_interaction", chapter=chapter_num))

            # Apply removals
            for item_obj in inv_delta.get("removed", []):
                if isinstance(item_obj, dict):
                    item = item_obj.get("item_id", "")
                    causal_actor = item_obj.get("causal_actor")
                else:
                    item = str(item_obj)
                    causal_actor = None

                norm_item = normalize_item_name(item)
                if not norm_item: continue
                if norm_item in curr_inv:
                    curr_inv.remove(norm_item)
                    # Sync world item ownership
                    item_world = current_state.world.get(norm_item)
                    if item_world:
                        item_world["owner"] = StateEntry(key="owner", element_type=NarrativeElementType.OBJECT)
                        item_world["owner"].update(StateSnapshot(value=None, chapter=chapter_num))
                        # Default dropped item location to character's current location
                        if loc_id:
                            item_world["location"] = StateEntry(key="location", element_type=NarrativeElementType.OBJECT)
                            item_world["location"].update(StateSnapshot(value=loc_id, chapter=chapter_num))
                            
                    if causal_actor == "UNKNOWN_ACTOR":
                        myst_id = f"mystery_ghost_inventory_{chapter_num}_{stable_hash(norm_item)[:4]}"
                        myst_entry = current_state.mysteries.setdefault(myst_id, {})
                        if "mystery_text" not in myst_entry: myst_entry["mystery_text"] = StateEntry(key="mystery_text", element_type=NarrativeElementType.MYSTERY)
                        myst_entry["mystery_text"].update(StateSnapshot(value=f"Item {norm_item} was tampered with or removed but the causal actor is unknown.", chapter=chapter_num))
                        if "status" not in myst_entry: myst_entry["status"] = StateEntry(key="status", element_type=NarrativeElementType.MYSTERY)
                        myst_entry["status"].update(StateSnapshot(value="unresolved", chapter=chapter_num))
                        if "type" not in myst_entry: myst_entry["type"] = StateEntry(key="type", element_type=NarrativeElementType.MYSTERY)
                        myst_entry["type"].update(StateSnapshot(value="ghost_interaction", chapter=chapter_num))

            update_field("inventory", curr_inv, "Inventory delta applied by LLM.")

        # 2. Apply World Updates
        for world_update in llm_delta.get("world_updates", []):
            item_id = normalize_item_name(world_update.get("item_id", ""))
            wtype = world_update.get("type", "object")
            loc = world_update.get("current_location_id")
            owner = world_update.get("owner_character_id")

            if not item_id or item_id in IMMOVABLE_STRUCTURES:
                continue

            is_new_item = item_id not in current_state.world or not current_state.world.get(item_id)
            validation = self._validator.evaluate_entity_proposal(
                entity_id=item_id,
                mention_hint=world_update.get("item_id", ""),
                is_new=is_new_item,
                confidence=1.0,
                chapter_data=chapter_data,
                flagged_entity_ids=flagged_entity_ids,
            )
            if not validation.accepted:
                logger.warning(f"ValidationEngine rejected world item proposal '{item_id}': {validation.reason}")
                delta.rejected_proposals.append({
                    "kind": "world_update", "entity_id": item_id, "reason": validation.reason,
                })
                continue
            item_confidence = validation.confidence if validation.confidence is not None else 1.0

            item_world = current_state.world.setdefault(item_id, {})

            # Preserve history rather than replacing the StateEntry outright — a prior version of
            # this loop always constructed a fresh StateEntry() here even for existing items,
            # silently discarding their entire prior history on every touch.
            def set_world_field(key: str, val: Any) -> None:
                if key not in item_world:
                    item_world[key] = StateEntry(key=key, element_type=NarrativeElementType.OBJECT)
                    old_val, old_conf = None, 0.0
                else:
                    old_snapshot = item_world[key].current
                    old_val = old_snapshot.value if old_snapshot else None
                    old_conf = old_snapshot.confidence if old_snapshot else 0.0
                if old_val == val:
                    return
                if old_val is not None:
                    contradiction = self._validator.check_field_contradiction(key, old_val, old_conf, val, item_confidence)
                    if contradiction.is_contradiction:
                        log_contradiction_mystery(item_id, contradiction.description)
                        if not contradiction.should_apply:
                            return
                item_world[key].update(StateSnapshot(value=val, chapter=chapter_num, confidence=item_confidence))

            set_world_field("type", wtype)
            if loc:
                set_world_field("location", loc)
            if owner:
                set_world_field("owner", owner)

        # 3. Apply Relationship Mutations
        for rel_mut in llm_delta.get("relationship_mutations", []):
            party_a = rel_mut.get("party_a")
            party_b = rel_mut.get("party_b")
            stance = rel_mut.get("stance")
            reasoning = rel_mut.get("reasoning", "Relationship updated by LLM.")

            if not party_a or not party_b or not stance:
                continue

            # Resolve through the same alias/proper-noun resolution as character_updates
            # above -- without this, the LLM's raw casing/mention text for an already-
            # established character (e.g. "Laurie") never matches its canonical id
            # ("laurie"), so `party in current_state.characters` below is always False for
            # a known character, and a second relationship record gets created under
            # "Laurie::Marlene" alongside the real "laurie::marlene". Caught by a
            # self-review pass.
            party_a = character_memory.resolve_character_id(party_a, current_state.characters)
            party_b = character_memory.resolve_character_id(party_b, current_state.characters)

            # Both parties must be established characters (from this chapter's deterministic
            # pass, a prior chapter, or this same LLM delta's own character_updates) or
            # independently evidence-supported — a relationship between two names that appear
            # nowhere else is exactly the kind of thing worth blocking rather than recording.
            rejected_party = None
            for party in (party_a, party_b):
                party_known = party in current_state.characters and bool(current_state.characters.get(party))
                if party_known:
                    continue
                party_validation = self._validator.evaluate_entity_proposal(
                    entity_id=party,
                    mention_hint=party,
                    is_new=True,
                    confidence=0.9,
                    chapter_data=chapter_data,
                    flagged_entity_ids=flagged_entity_ids,
                )
                if not party_validation.accepted:
                    rejected_party = (party, party_validation.reason)
                    break
            if rejected_party:
                logger.warning(
                    f"ValidationEngine rejected relationship proposal '{party_a}'::'{party_b}': "
                    f"party '{rejected_party[0]}' unsupported ({rejected_party[1]})"
                )
                delta.rejected_proposals.append({
                    "kind": "relationship_mutation", "entity_id": f"{party_a}::{party_b}",
                    "reason": f"party '{rejected_party[0]}' unsupported: {rejected_party[1]}",
                })
                continue

            rel_id = f"{party_a}::{party_b}"
            rev_id = f"{party_b}::{party_a}"
            if rev_id in current_state.relationships:
                rel_id = rev_id

            rel_entry = current_state.relationships.setdefault(rel_id, {})

            if "relationship_label" not in rel_entry:
                rel_entry["relationship_label"] = StateEntry(key="relationship_label", element_type=NarrativeElementType.CHARACTER)
                change_type = StateChangeType.INTRODUCTION
                old_val = None
            else:
                change_type = StateChangeType.EVOLUTION
                old_val = rel_entry["relationship_label"].current.value if rel_entry["relationship_label"].current else None

            if old_val != stance:
                rel_entry["relationship_label"].update(StateSnapshot(
                    value=stance,
                    chapter=chapter_num,
                    confidence=0.9,
                    reasoning=reasoning
                ))
                delta.changes.append(StateChange(
                    change_type=change_type,
                    target_type=NarrativeElementType.CHARACTER,
                    target_id=rel_id,
                    field_key="relationship_label",
                    old_value=old_val,
                    new_value=stance,
                    confidence=0.9,
                    reasoning=reasoning
                ))

        # 4. Apply Promises Delta
        for prom_delta in llm_delta.get("promises_delta", []):
            prom_id = prom_delta.get("promise_id")
            text = prom_delta.get("text")
            speaker = prom_delta.get("speaker_id")
            listener = prom_delta.get("listener_id")
            status = prom_delta.get("status", "OPEN")
            reasoning = prom_delta.get("reasoning", "Promise updated by LLM.")

            if not prom_id or not text or not speaker:
                continue

            prom_entry = current_state.promises.setdefault(prom_id, {})

            def update_promise_field(key: str, val: Any):
                if key not in prom_entry:
                    prom_entry[key] = StateEntry(key=key, element_type=NarrativeElementType.PROMISE)
                    old_val = None
                else:
                    old_val = prom_entry[key].current.value if prom_entry[key].current else None

                if old_val != val:
                    prom_entry[key].update(StateSnapshot(
                        value=val,
                        chapter=chapter_num,
                        confidence=0.95,
                        reasoning=reasoning
                    ))

            update_promise_field("promise_text", text)
            update_promise_field("speaker_id", speaker)
            update_promise_field("listener_id", listener)
            update_promise_field("status", status)
            update_promise_field("chapter_made", chapter_num)

            # Record change in delta
            delta.changes.append(StateChange(
                change_type=StateChangeType.EVOLUTION,
                target_type=NarrativeElementType.PROMISE,
                target_id=prom_id,
                field_key="status",
                old_value=None,
                new_value=status,
                confidence=0.95,
                reasoning=reasoning
            ))

        # 4a. Apply Threats Delta
        for threat_delta in llm_delta.get("threats_delta", []):
            threat_id = threat_delta.get("threat_id")
            text = threat_delta.get("text")
            target = threat_delta.get("target_id")
            source = threat_delta.get("source_id")
            status = threat_delta.get("status", "ACTIVE")
            reasoning = threat_delta.get("reasoning", "Threat updated by LLM.")

            if not threat_id or not text: continue
            threat_entry = current_state.threats.setdefault(threat_id, {})

            def update_threat_field(key: str, val: Any):
                if key not in threat_entry:
                    threat_entry[key] = StateEntry(key=key, element_type=NarrativeElementType.THREAT)
                threat_entry[key].update(StateSnapshot(value=val, chapter=chapter_num, confidence=0.95, reasoning=reasoning))

            update_threat_field("threat_text", text)
            update_threat_field("target_id", target)
            update_threat_field("source_id", source)
            update_threat_field("status", status)
            update_threat_field("chapter_made", chapter_num)

            delta.changes.append(StateChange(
                change_type=StateChangeType.EVOLUTION,
                target_type=NarrativeElementType.THREAT,
                target_id=threat_id,
                field_key="status",
                old_value=None,
                new_value=status,
                confidence=0.95,
                reasoning=reasoning
            ))

        # 4b. Apply Themes Delta
        for theme_delta in llm_delta.get("themes_delta", []):
            theme_id = theme_delta.get("theme_id")
            desc = theme_delta.get("description")
            reasoning = theme_delta.get("reasoning", "Theme updated by LLM.")

            if not theme_id or not desc: continue
            theme_entry = current_state.themes.setdefault(theme_id, {})
            
            if "description" not in theme_entry:
                theme_entry["description"] = StateEntry(key="description", element_type=NarrativeElementType.THEME)
            theme_entry["description"].update(StateSnapshot(value=desc, chapter=chapter_num, confidence=0.9, reasoning=reasoning))

        # 4c. Apply Motifs Delta
        for motif_delta in llm_delta.get("motifs_delta", []):
            motif_id = motif_delta.get("motif_id")
            desc = motif_delta.get("description")
            reasoning = motif_delta.get("reasoning", "Motif updated by LLM.")

            if not motif_id or not desc: continue
            motif_entry = current_state.motifs.setdefault(motif_id, {})
            
            if "description" not in motif_entry:
                motif_entry["description"] = StateEntry(key="description", element_type=NarrativeElementType.MOTIF)
            motif_entry["description"].update(StateSnapshot(value=desc, chapter=chapter_num, confidence=0.9, reasoning=reasoning))

        # 4d. Apply Timeline Events — explicit, structured events proposed by the World+Timeline
        # LLM stage. This is the first real source of chapter_data-independent timeline content:
        # previously current_state.timeline was populated only by the death/moves_to/acquires
        # inference hack below (section "Synchronize LLM updates..."), since the deterministic
        # TimelineMemory path has nothing to work with until relation extraction feeds it (see
        # Pipeline._extract_relations). Kept additive alongside that hack rather than replacing it,
        # since TimelineInspector's post-mortem detection depends on the "dies" predicate it emits.
        for idx, event in enumerate(llm_delta.get("timeline_events", [])):
            subject = event.get("subject")
            predicate = event.get("predicate")
            obj = event.get("object")
            if not subject or not predicate:
                continue

            timeline_entry = {
                "chapter": chapter_num,
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "time": event.get("time"),
                "source": "llm_timeline_stage",
            }
            current_state.timeline.append(timeline_entry)

            event_id = f"ch{chapter_num}_llm_evt{idx}"
            delta.changes.append(StateChange(
                change_type=StateChangeType.INTRODUCTION,
                target_type=NarrativeElementType.EVENT,
                target_id=event_id,
                field_key="description",
                new_value=f"{subject} {predicate} {obj or ''}".strip(),
                confidence=event.get("confidence", 0.8),
                reasoning="Timeline event proposed by World+Timeline LLM stage.",
            ))

        # 5. Extract and persist LLM structural mysteries
        delta.structural_mysteries = []
        for mystery in llm_delta.get("structural_mysteries", []):
            issue_type = mystery.get("issue_type")
            severity = mystery.get("severity", "WARNING")
            desc = mystery.get("description")
            entities = mystery.get("related_entities", [])

            if not issue_type or not desc:
                continue

            delta.structural_mysteries.append(mystery)

            # Persist in state mysteries
            myst_id = f"mystery_{issue_type.lower()}_{chapter_num}_{stable_hash(desc)[:4]}"
            myst_entry = current_state.mysteries.setdefault(myst_id, {})

            def update_myst_field(key: str, val: Any):
                if key not in myst_entry:
                    myst_entry[key] = StateEntry(key=key, element_type=NarrativeElementType.MYSTERY)
                myst_entry[key].update(StateSnapshot(value=val, chapter=chapter_num))

            update_myst_field("mystery_text", desc)
            update_myst_field("status", "unresolved")
            update_myst_field("chapter_introduced", chapter_num)
            update_myst_field("severity", severity)
            update_myst_field("issue_type", issue_type)
            update_myst_field("related_entities", entities)

            delta.changes.append(StateChange(
                change_type=StateChangeType.INTRODUCTION,
                target_type=NarrativeElementType.MYSTERY,
                target_id=myst_id,
                field_key="status",
                old_value=None,
                new_value="unresolved",
                confidence=0.9,
                reasoning=f"LLM contradiction flagged: {desc}"
            ))

        # Synchronize LLM updates with current_state.timeline for static inspectors
        for char_update in llm_delta.get("character_updates", []):
            char_id = char_update.get("character_id")
            if not char_id:
                continue
            
            # Check for death in traits_mutated
            is_dead = False
            traits = char_update.get("traits_mutated", {})
            for tname, tdata in traits.items():
                tval = tdata.get("value")
                if tval == "dead" or (isinstance(tval, list) and "dead" in tval):
                    is_dead = True
                    
            loc = char_update.get("current_location_id")
            if is_dead:
                current_state.timeline.append({
                    "chapter": chapter_num,
                    "subject": char_id,
                    "predicate": "dies",
                    "object": loc if loc else "unknown"
                })
            else:
                if loc:
                    current_state.timeline.append({
                        "chapter": chapter_num,
                        "subject": char_id,
                        "predicate": "moves_to",
                        "object": loc
                    })
                # Check for inventory actions
                inv_delta = char_update.get("inventory_delta", {})
                for item_obj in inv_delta.get("added", []):
                    item = item_obj.get("item_id", "") if isinstance(item_obj, dict) else str(item_obj)
                    if not item: continue
                    current_state.timeline.append({
                        "chapter": chapter_num,
                        "subject": char_id,
                        "predicate": "acquires",
                        "object": item
                    })
                for item_obj in inv_delta.get("removed", []):
                    item = item_obj.get("item_id", "") if isinstance(item_obj, dict) else str(item_obj)
                    if not item: continue
                    current_state.timeline.append({
                        "chapter": chapter_num,
                        "subject": char_id,
                        "predicate": "discards",
                        "object": item
                    })

        # Prepare summary
        delta.summary = (
            f"Chapter {chapter_num} processed via Hybrid LLM State Engine. "
            f"Updated {len(llm_delta.get('character_updates', []))} characters, "
            f"mutated {len(llm_delta.get('relationship_mutations', []))} relationships, "
            f"adjusted {len(llm_delta.get('promises_delta', []))} promises. "
            f"Flagged {len(delta.structural_mysteries)} structural mysteries. "
            f"ValidationEngine rejected {len(delta.rejected_proposals)} proposals."
        )

        return delta
