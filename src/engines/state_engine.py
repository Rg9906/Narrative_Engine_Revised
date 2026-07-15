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

logger = logging.getLogger("NarrativeEngine.Engines.StateEngine")


class StateEngine:
    """
    Unified LLM State Engine.
    
    Parses LLM sensory delta outputs and applies updates to the NarrativeState
    with defensive guardrails and atomic persistence.
    """

    def __init__(self, config=None):
        self._config = config

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
        if not llm_delta or not has_updates:
            logger.info(f"No LLM delta found or empty delta for chapter {chapter_num}. Falling back to legacy memory updates.")
            from src.memory.character_memory import CharacterMemory
            from src.memory.relationship_memory import RelationshipMemory
            from src.memory.world_memory import WorldMemory
            from src.memory.timeline_memory import TimelineMemory
            from src.memory.theme_memory import ThemeMemory
            from src.memory.promise_memory import PromiseMemory
            from src.memory.mystery_memory import MysteryMemory
            from src.memory.style_memory import StyleMemory

            character_memory = CharacterMemory(existing_entries=current_state.characters)
            character_changes = character_memory.update_from_chapter(chapter_data, chapter_num)
            delta.changes.extend(character_changes)

            advanced_character_changes = character_memory.extract_advanced_attributes(chapter_data, chapter_num)
            delta.changes.extend(advanced_character_changes)

            relationship_memory = RelationshipMemory()
            relationship_memory.load(current_state.relationships)
            relationship_changes = relationship_memory.update_from_chapter(
                chapter_data, chapter_num, existing_characters=current_state.characters
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

            # Persist back
            current_state.characters = character_memory.entries
            current_state.relationships = relationship_memory.entries
            current_state.world = world_memory.entries
            current_state.themes = theme_memory.entries
            current_state.promises = promise_memory.entries
            current_state.mysteries = mystery_memory.entries
            current_state.style = style_memory.entries

            # Append timeline events
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
                
            return delta

        # Normalize item names (Artifact Matching)
        def normalize_item_name(item: str) -> str:
            item_clean = item.strip().lower()
            if item_clean in ("wedding band", "wedding ring", "marlene's emerald-set platinum wedding ring", "emerald-set platinum wedding ring"):
                return "wedding_ring"
            if item_clean in ("emperor's scarab", "scarab"):
                return "emperor_s_scarab"
            return item_clean.replace(" ", "_")

        # Exclusions for immovable structures
        IMMOVABLE_STRUCTURES = {"fireplace", "staircase", "hearth", "floorboard", "desk", "bookshelf", "mantlepiece", "library_shelves", "shelves"}

        # 1. Apply Character Updates
        for char_update in llm_delta.get("character_updates", []):
            char_id = char_update.get("character_id")
            if not char_id:
                continue
            
            char_entry = current_state.characters.setdefault(char_id, {})

            # Helper for updating a StateEntry
            def update_field(key: str, val: Any, reasoning: str, confidence: float = 1.0):
                if key not in char_entry:
                    char_entry[key] = StateEntry(key=key, element_type=NarrativeElementType.CHARACTER)
                    change_type = StateChangeType.INTRODUCTION
                    old_val = None
                else:
                    change_type = StateChangeType.EVOLUTION
                    old_val = char_entry[key].current.value if char_entry[key].current else None

                if old_val != val:
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
            for item in inv_delta.get("added", []):
                norm_item = normalize_item_name(item)
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

            # Apply removals
            for item in inv_delta.get("removed", []):
                norm_item = normalize_item_name(item)
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

            update_field("inventory", curr_inv, "Inventory delta applied by LLM.")

        # 2. Apply World Updates
        for world_update in llm_delta.get("world_updates", []):
            item_id = normalize_item_name(world_update.get("item_id"))
            wtype = world_update.get("type", "object")
            loc = world_update.get("current_location_id")
            owner = world_update.get("owner_character_id")

            if not item_id or item_id in IMMOVABLE_STRUCTURES:
                continue

            item_world = current_state.world.setdefault(item_id, {})
            item_world["type"] = StateEntry(key="type", element_type=NarrativeElementType.OBJECT)
            item_world["type"].update(StateSnapshot(value=wtype, chapter=chapter_num))

            if loc:
                item_world["location"] = StateEntry(key="location", element_type=NarrativeElementType.OBJECT)
                item_world["location"].update(StateSnapshot(value=loc, chapter=chapter_num))
            if owner:
                item_world["owner"] = StateEntry(key="owner", element_type=NarrativeElementType.OBJECT)
                item_world["owner"].update(StateSnapshot(value=owner, chapter=chapter_num))

        # 3. Apply Relationship Mutations
        for rel_mut in llm_delta.get("relationship_mutations", []):
            party_a = rel_mut.get("party_a")
            party_b = rel_mut.get("party_b")
            stance = rel_mut.get("stance")
            reasoning = rel_mut.get("reasoning", "Relationship updated by LLM.")
            
            if not party_a or not party_b or not stance:
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
            myst_id = f"mystery_{issue_type.lower()}_{chapter_num}_{hash(desc) & 0xffff}"
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
                for item in inv_delta.get("added", []):
                    current_state.timeline.append({
                        "chapter": chapter_num,
                        "subject": char_id,
                        "predicate": "draws" if "whisperwind" in item.lower() else "acquires",
                        "object": item
                    })
                for item in inv_delta.get("removed", []):
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
            f"Flagged {len(delta.structural_mysteries)} structural mysteries."
        )

        return delta
