import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional

logger = logging.getLogger("NarrativeEngine.Pipeline.ContextRetriever")

class ContextRetriever:
    """
    Production-grade RAG Context Preprocessing Pipeline.
    Stage 1: Boundary-Safe Entity and Location Scanner.
    Stage 2: Four-Tier Surgical State Hydration (Profiles, Relationships, Promises, Clues).
    Stage 3: Token-budgeted XML Context Compilation.
    """

    def __init__(self, config=None):
        self._config = config
        self._memory_dir = Path("data/memory")
        if config and hasattr(config, "memory_dir"):
            self._memory_dir = Path(config.memory_dir)

    def retrieve_context(self, raw_text: str) -> Tuple[Optional[str], List[str]]:
        """
        Runs entity pre-scans, hydrates data structures, compiles budgeted XML block.
        Returns a tuple: (context_block_str, list_of_active_character_ids)
        """
        # Wrap database loading in try-except block to handle cold start safely
        data_sources = self._load_data_sources()
        char_data = data_sources["characters"]
        relationships_data = data_sources["relationships"]
        promises_data = data_sources["promises"]
        world_data = data_sources["world"]

        if not char_data:
            logger.info("Character database is empty or missing. Skipping RAG context.")
            return None, []

        # Stage 1: Robust Boundary-Safe Entity & Location Detection
        active_characters = self._detect_active_characters(raw_text, char_data)
        if not active_characters:
            return None, []

        active_locations = self._detect_active_locations(raw_text, world_data)
        
        # Fallback: if no locations mentioned, use active characters' current locations
        if not active_locations:
            for char_id in active_characters:
                char_profile = char_data.get(char_id, {})
                loc_entry = char_profile.get("location", {})
                if isinstance(loc_entry, dict):
                    loc_val = loc_entry.get("current", {}).get("value")
                    if loc_val:
                        active_locations.add(str(loc_val).lower())

        # Stage 2 & 3: Four-Tier Surgical Hydration & Token Budgeting
        context_str = self._hydrate_and_compile(
            active_characters=active_characters,
            active_locations=active_locations,
            char_data=char_data,
            relationships_data=relationships_data,
            promises_data=promises_data,
            world_data=world_data
        )

        return context_str, sorted(list(active_characters))

    def _load_data_sources(self) -> Dict[str, Dict[str, Any]]:
        """
        Loads all required memory databases safely from disk.
        Returns empty structures if files do not exist or fail to parse.
        """
        char_data = {}
        relationships_data = {}
        promises_data = {}
        world_data = {}

        # 1. Try global state narrative_state.json as fallback source
        state_path = self._memory_dir / "narrative_state.json"
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                    char_data = sdata.get("characters", {})
                    relationships_data = sdata.get("relationships", {})
                    promises_data = sdata.get("promises", {})
                    world_data = sdata.get("world", {})
            except Exception as e:
                logger.warning(f"Graceful fallback: Failed to load narrative_state.json: {e}")

        # 2. Try loading from individual legacy files as fallback
        char_mem_path = self._memory_dir / "character_memory.json"
        if char_mem_path.exists():
            try:
                with open(char_mem_path, "r", encoding="utf-8") as f:
                    char_data.update(json.load(f))
            except Exception as e:
                logger.warning(f"Graceful fallback: Failed to load character_memory.json: {e}")

        rel_mem_path = self._memory_dir / "relationship_memory.json"
        if rel_mem_path.exists():
            try:
                with open(rel_mem_path, "r", encoding="utf-8") as f:
                    relationships_data.update(json.load(f))
            except Exception as e:
                logger.warning(f"Graceful fallback: Failed to load relationship_memory.json: {e}")

        world_mem_path = self._memory_dir / "world_memory.json"
        if world_mem_path.exists():
            try:
                with open(world_mem_path, "r", encoding="utf-8") as f:
                    wdata = json.load(f)
                    if isinstance(wdata, dict):
                        if "world" in wdata:
                            world_data.update(wdata.get("world", {}))
                        else:
                            world_data.update(wdata)
                        if "promises" in wdata:
                            promises_data.update(wdata.get("promises", {}))
            except Exception as e:
                logger.warning(f"Graceful fallback: Failed to load world_memory.json: {e}")

        vows_path = self._memory_dir / "vows.json"
        if vows_path.exists():
            try:
                with open(vows_path, "r", encoding="utf-8") as f:
                    promises_data.update(json.load(f))
            except Exception as e:
                logger.warning(f"Graceful fallback: Failed to load vows.json: {e}")

        # 3. Load from the new folder-based file database (data/profiles, data/relationships, data/clues, data/promises)
        profiles_dir = Path("data/profiles")
        if self._config and hasattr(self._config, "profiles_dir"):
            profiles_dir = self._config.profiles_dir
        if profiles_dir.exists():
            for fpath in profiles_dir.glob("*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        cdata = json.load(f)
                        if isinstance(cdata, dict):
                            char_id = fpath.stem.lower()
                            if char_id in cdata and isinstance(cdata[char_id], dict):
                                char_data.update(cdata)
                            else:
                                char_data[char_id] = cdata
                except Exception as e:
                    logger.warning(f"Failed to load profile from {fpath.name}: {e}")

        relationships_dir = Path("data/relationships")
        if self._config and hasattr(self._config, "relationships_dir"):
            relationships_dir = self._config.relationships_dir
        if relationships_dir.exists():
            for fpath in relationships_dir.glob("*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        rdata = json.load(f)
                        if isinstance(rdata, dict):
                            stem = fpath.stem.lower()
                            rel_key = stem.replace("__", "::")
                            if rel_key in rdata and isinstance(rdata[rel_key], dict):
                                relationships_data.update(rdata)
                            else:
                                relationships_data[rel_key] = rdata
                except Exception as e:
                    logger.warning(f"Failed to load relationship from {fpath.name}: {e}")

        promises_dir = Path("data/promises")
        if self._config and hasattr(self._config, "promises_dir"):
            promises_dir = self._config.promises_dir
        if promises_dir.exists():
            for fpath in promises_dir.glob("*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        pdata = json.load(f)
                        if isinstance(pdata, dict):
                            promise_id = fpath.stem.lower()
                            if promise_id in pdata and isinstance(pdata[promise_id], dict):
                                promises_data.update(pdata)
                            else:
                                promises_data[promise_id] = pdata
                except Exception as e:
                    logger.warning(f"Failed to load promise from {fpath.name}: {e}")

        clues_dir = Path("data/clues")
        if self._config and hasattr(self._config, "clues_dir"):
            clues_dir = self._config.clues_dir
        if clues_dir.exists():
            for fpath in clues_dir.glob("*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        cldata = json.load(f)
                        if isinstance(cldata, dict):
                            clue_id = fpath.stem.lower()
                            if clue_id in cldata and isinstance(cldata[clue_id], dict):
                                world_data.update(cldata)
                            else:
                                world_data[clue_id] = cldata
                except Exception as e:
                    logger.warning(f"Failed to load clue from {fpath.name}: {e}")

        return {
            "characters": char_data,
            "relationships": relationships_data,
            "promises": promises_data,
            "world": world_data,
        }

    def _detect_active_characters(self, raw_text: str, char_data: Dict[str, Any]) -> Set[str]:
        """
        Performs boundary-safe regex matching for character IDs and aliases to prevent false substring collisions.
        """
        active = set()
        for char_id, profile in char_data.items():
            aliases = {char_id.lower()}
            
            if "_" in char_id:
                aliases.add(char_id.replace("_", " ").lower())

            # Fetch canonical name
            canonical_entry = profile.get("canonical_name", {})
            if canonical_entry:
                current_val = canonical_entry.get("current", {}).get("value")
                if current_val:
                    aliases.add(str(current_val).lower())

            # Fetch aliases list
            aliases_entry = profile.get("aliases", {}) or profile.get("aliases_discovered", {})
            if aliases_entry:
                aliases_val = aliases_entry.get("current", {}).get("value", [])
                if isinstance(aliases_val, list):
                    for alias in aliases_val:
                        aliases.add(str(alias).lower())
                elif isinstance(aliases_val, str):
                    aliases.add(aliases_val.lower())

            # Match using word boundaries to ensure safety
            for alias in aliases:
                if not alias or len(alias.strip()) == 0:
                    continue
                pattern = re.compile(rf"\b{re.escape(alias.strip())}\b", re.IGNORECASE)
                if pattern.search(raw_text):
                    active.add(char_id)
                    break
        return active

    def _detect_active_locations(self, raw_text: str, world_data: Dict[str, Any]) -> Set[str]:
        """
        Scans raw text case-insensitively for location IDs and display names using word-boundary regexes.
        """
        active = set()
        for elem_id, profile in world_data.items():
            type_entry = profile.get("type", {})
            if isinstance(type_entry, dict):
                type_val = type_entry.get("current", {}).get("value")
                if type_val != "location":
                    continue
            else:
                continue

            aliases = {elem_id.lower()}
            if "_" in elem_id:
                aliases.add(elem_id.replace("_", " ").lower())

            # Capture canonical name/description variants if available
            canonical_entry = profile.get("canonical_name", {}) or profile.get("name", {})
            if isinstance(canonical_entry, dict):
                current_val = canonical_entry.get("current", {}).get("value")
                if current_val:
                    aliases.add(str(current_val).lower())

            # Perform boundary-safe regex matching
            for alias in aliases:
                if not alias or len(alias.strip()) == 0:
                    continue
                pattern = re.compile(rf"\b{re.escape(alias.strip())}\b", re.IGNORECASE)
                if pattern.search(raw_text):
                    active.add(elem_id)
                    break
        return active

    def _hydrate_and_compile(
        self,
        active_characters: Set[str],
        active_locations: Set[str],
        char_data: Dict[str, Any],
        relationships_data: Dict[str, Any],
        promises_data: Dict[str, Any],
        world_data: Dict[str, Any]
    ) -> str:
        """
        Hydrates Tier A, B, C, D and compiles them into a token-budgeted XML structure.
        """
        # Tier A: Characters Profile XML Parts
        char_xmls = []
        for char_id in sorted(list(active_characters)):
            profile = char_data[char_id]
            canonical_name = profile.get("canonical_name", {}).get("current", {}).get("value", char_id.capitalize())
            location = profile.get("location", {}).get("current", {}).get("value", "unknown")
            
            inventory_val = profile.get("inventory", {}).get("current", {}).get("value", [])
            inventory = ", ".join(inventory_val) if isinstance(inventory_val, list) else str(inventory_val)
            if not inventory:
                inventory = "none"

            goals_val = profile.get("goals", {}).get("current", {}).get("value", [])
            goals = "; ".join(goals_val) if isinstance(goals_val, list) else str(goals_val)
            if not goals:
                goals = "none"

            fears_val = profile.get("fears", {}).get("current", {}).get("value", [])
            fears = "; ".join(fears_val) if isinstance(fears_val, list) else str(fears_val)
            if not fears:
                fears = "none"

            traits = []
            for k, entry in profile.items():
                if k not in ("canonical_name", "location", "inventory", "goals", "fears", "aliases", "aliases_discovered"):
                    if isinstance(entry, dict):
                        val = entry.get("current", {}).get("value")
                        if val is not None:
                            traits.append(f"{k}={val}")
            traits_str = ", ".join(traits) if traits else "none"

            char_xmls.append(
                f"    <Character id=\"{char_id}\">\n"
                f"      <Name>{canonical_name}</Name>\n"
                f"      <Location>{location}</Location>\n"
                f"      <Inventory>{inventory}</Inventory>\n"
                f"      <Goals>{goals}</Goals>\n"
                f"      <Fears>{fears}</Fears>\n"
                f"      <Traits>{traits_str}</Traits>\n"
                f"    </Character>"
            )

        # Tier D: Physical Clues XML Parts
        clue_xmls = []
        for elem_id, profile in sorted(world_data.items()):
            # Check type
            type_entry = profile.get("type", {})
            type_val = type_entry.get("current", {}).get("value") if isinstance(type_entry, dict) else None
            if type_val != "object":
                continue

            # Check location
            loc_entry = profile.get("location", {})
            loc_val = loc_entry.get("current", {}).get("value") if isinstance(loc_entry, dict) else None
            if not loc_val or str(loc_val).lower() not in active_locations:
                continue

            status_entry = profile.get("status", {}) or profile.get("state", {})
            status_val = status_entry.get("current", {}).get("value", "present") if isinstance(status_entry, dict) else "present"

            desc_entry = profile.get("description", {}) or profile.get("reasoning", {})
            desc_val = desc_entry.get("current", {}).get("value", "") if isinstance(desc_entry, dict) else ""

            clue_xmls.append(
                f"    <Clue id=\"{elem_id}\">\n"
                f"      <Location>{loc_val}</Location>\n"
                f"      <Status>{status_val}</Status>\n"
                f"      <Description>{desc_val}</Description>\n"
                f"    </Clue>"
            )

        # Tier B: Relationships XML Parts
        relationship_xmls = []
        char_list = sorted(list(active_characters))
        for i in range(len(char_list)):
            for j in range(i + 1, len(char_list)):
                c1, c2 = char_list[i], char_list[j]
                # Check both key directions
                key1 = f"{c1}::{c2}"
                key2 = f"{c2}::{c1}"
                rel_entry = relationships_data.get(key1) or relationships_data.get(key2)
                if rel_entry:
                    label_entry = rel_entry.get("relationship_label") or rel_entry.get("stance")
                    label_val = label_entry.get("current", {}).get("value", "UNKNOWN") if isinstance(label_entry, dict) else "UNKNOWN"

                    reason_entry = rel_entry.get("reasoning") or rel_entry.get("description")
                    reason_val = reason_entry.get("current", {}).get("value", "") if isinstance(reason_entry, dict) else ""

                    relationship_xmls.append(
                        f"    <Relationship party_a=\"{c1}\" party_b=\"{c2}\">\n"
                        f"      <Stance>{label_val}</Stance>\n"
                        f"      <Reasoning>{reason_val}</Reasoning>\n"
                        f"    </Relationship>"
                    )

        # Tier C: Unresolved Promises XML Parts
        promise_xmls = []
        for pid, pentry in sorted(promises_data.items()):
            if not isinstance(pentry, dict):
                continue
            
            status_entry = pentry.get("status", {})
            status = status_entry.get("current", {}).get("value", "OPEN")
            
            if status not in ("OPEN", "unresolved", "unfulfilled"):
                continue

            speaker_entry = pentry.get("speaker_id", {})
            speaker = speaker_entry.get("current", {}).get("value", "unknown")

            listener_entry = pentry.get("listener_id", {})
            listener = listener_entry.get("current", {}).get("value", "unknown")

            if speaker in active_characters or listener in active_characters:
                text_entry = pentry.get("promise_text") or pentry.get("text", {})
                text = text_entry.get("current", {}).get("value", "") if isinstance(text_entry, dict) else str(text_entry)

                chapter_entry = pentry.get("chapter_made", {})
                chapter = chapter_entry.get("current", {}).get("value", "unknown")

                promise_xmls.append(
                    f"    <Promise speaker=\"{speaker}\" listener=\"{listener}\" status=\"{status}\" chapter_made=\"{chapter}\">\n"
                    f"      {text.strip()}\n"
                    f"    </Promise>"
                )

        # Stage 3: Token budget XML assembly
        # XML tags layout size overhead
        wrapper_start = "<StoryContext>\n"
        char_start, char_end = "  <ActiveCharacters>\n", "  </ActiveCharacters>\n"
        clue_start, clue_end = "  <SceneClues>\n", "  </SceneClues>\n"
        rel_start, rel_end = "  <ActiveRelationships>\n", "  </ActiveRelationships>\n"
        prom_start, prom_end = "  <OpenPromises>\n", "  </OpenPromises>\n"
        wrapper_end = "</StoryContext>"

        # Compile Tiers A & D (Characters & Clues)
        chars_xml_str = "\n".join(char_xmls)
        clues_xml_str = "\n".join(clue_xmls)

        current_xml = wrapper_start
        if char_xmls:
            current_xml += char_start + chars_xml_str + "\n" + char_end
        if clue_xmls:
            current_xml += clue_start + clues_xml_str + "\n" + clue_end

        # Calculate budget for Relationships and Promises
        budget = 3000 - len(current_xml) - len(wrapper_end) - 100 # Add a small buffer

        included_rels = []
        included_proms = []

        if budget > 0:
            # Try to add Relationships one by one
            for rel in relationship_xmls:
                if len(rel) + len(rel_start) + len(rel_end) < budget:
                    included_rels.append(rel)
                    budget -= len(rel)
                else:
                    logger.warning("RAG token limit: relationship entry truncated.")
            
            # Try to add Promises one by one
            for prom in promise_xmls:
                if len(prom) + len(prom_start) + len(prom_end) < budget:
                    included_proms.append(prom)
                    budget -= len(prom)
                else:
                    logger.warning("RAG token limit: promise entry truncated.")

        # Build final budgeted XML block
        if included_rels:
            current_xml += rel_start + "\n".join(included_rels) + "\n" + rel_end
        if included_proms:
            current_xml += prom_start + "\n".join(included_proms) + "\n" + prom_end

        current_xml += wrapper_end
        return current_xml
