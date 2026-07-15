import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional

logger = logging.getLogger("NarrativeEngine.Pipeline.ContextRetriever")

class ContextRetriever:
    """
    RAG Context Preprocessing Pipeline.
    Stage 1: Pre-scans raw chapter text to detect characters mentioned.
    Stage 2: Retrieves active profiles and unresolved promises to build a focused prompt context.
    """

    def __init__(self, config=None):
        self._config = config
        self._memory_dir = Path("data/memory")
        if config and hasattr(config, "memory_dir"):
            self._memory_dir = Path(config.memory_dir)

    def retrieve_context(self, raw_text: str) -> Tuple[Optional[str], List[str]]:
        """
        Scans raw text, hydrates profile/inventory/promises context, and compiles XML context block.
        Returns a tuple: (context_block_str, list_of_active_character_ids)
        """
        char_mem_path = self._memory_dir / "character_memory.json"
        if not char_mem_path.exists():
            logger.info("character_memory.json does not exist. RAG context skipped.")
            return None, []

        try:
            with open(char_mem_path, "r", encoding="utf-8") as f:
                char_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load character_memory.json: {e}")
            return None, []

        # Stage 1: Pre-scan Entity Scanner
        active_characters = self._detect_active_characters(raw_text, char_data)
        if not active_characters:
            return None, []

        # Stage 2: Surgical State Hydration
        profiles_xml = self._hydrate_profiles(active_characters, char_data)
        promises_xml = self._hydrate_promises(active_characters)

        # Stage 3: Context-Aware Prompt Compilation
        context_block = []
        if profiles_xml:
            context_block.append(profiles_xml)
        if promises_xml:
            context_block.append(promises_xml)

        if not context_block:
            return None, sorted(list(active_characters))

        return "\n".join(context_block), sorted(list(active_characters))

    def _detect_active_characters(self, raw_text: str, char_data: Dict[str, Any]) -> Set[str]:
        active = set()
        for char_id, profile in char_data.items():
            names_to_match = {char_id.lower()}
            
            # Add spacing variant if id contains underscores
            if "_" in char_id:
                names_to_match.add(char_id.replace("_", " ").lower())

            # Add canonical name
            canonical_entry = profile.get("canonical_name", {})
            if canonical_entry:
                current_val = canonical_entry.get("current", {}).get("value")
                if current_val:
                    names_to_match.add(current_val.lower())

            # Add aliases if present
            aliases_entry = profile.get("aliases", {})
            if aliases_entry:
                aliases = aliases_entry.get("current", {}).get("value", [])
                if isinstance(aliases, list):
                    for alias in aliases:
                        names_to_match.add(alias.lower())
                elif isinstance(aliases, str):
                    names_to_match.add(aliases.lower())

            # Scan raw_text case-insensitively with word boundaries
            for name in names_to_match:
                if not name:
                    continue
                pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
                if pattern.search(raw_text):
                    active.add(char_id)
                    break
        return active

    def _hydrate_profiles(self, active_characters: Set[str], char_data: Dict[str, Any]) -> str:
        xml_parts = ["<ActiveCharacterProfiles>"]
        for char_id in sorted(list(active_characters)):
            profile = char_data[char_id]
            canonical_name = profile.get("canonical_name", {}).get("current", {}).get("value", char_id.capitalize())
            location = profile.get("location", {}).get("current", {}).get("value", "unknown")
            
            # Extract active inventory items
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

            # Extract other traits
            traits = []
            for k, entry in profile.items():
                if k not in ("canonical_name", "location", "inventory", "goals", "fears"):
                    if isinstance(entry, dict):
                        val = entry.get("current", {}).get("value")
                        if val is not None:
                            traits.append(f"{k}={val}")
            traits_str = ", ".join(traits) if traits else "none"

            xml_parts.append(
                f"  <Character id=\"{char_id}\">\n"
                f"    <Name>{canonical_name}</Name>\n"
                f"    <Location>{location}</Location>\n"
                f"    <Inventory>{inventory}</Inventory>\n"
                f"    <Goals>{goals}</Goals>\n"
                f"    <Fears>{fears}</Fears>\n"
                f"    <Traits>{traits_str}</Traits>\n"
                f"  </Character>"
            )
        xml_parts.append("</ActiveCharacterProfiles>")
        return "\n".join(xml_parts)

    def _hydrate_promises(self, active_characters: Set[str]) -> str:
        # Check world_memory.json first, then fall back to narrative_state.json
        world_mem_path = self._memory_dir / "world_memory.json"
        state_path = self._memory_dir / "narrative_state.json"
        
        promises_dict = {}
        if world_mem_path.exists():
            try:
                with open(world_mem_path, "r", encoding="utf-8") as f:
                    wdata = json.load(f)
                    promises_dict = wdata.get("promises", {})
            except Exception as e:
                logger.warning(f"Failed to load world_memory.json: {e}")

        if not promises_dict and state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                    promises_dict = sdata.get("promises", {})
            except Exception as e:
                logger.warning(f"Failed to load narrative_state.json: {e}")

        if not promises_dict:
            return ""

        xml_parts = ["<ActivePromises>"]
        has_promises = False
        
        for pid, pentry in promises_dict.items():
            if not isinstance(pentry, dict):
                continue
                
            status_entry = pentry.get("status", {})
            status = status_entry.get("current", {}).get("value", "OPEN")
            
            # Pull unresolved promises
            if status not in ("OPEN", "unresolved", "unfulfilled"):
                continue

            speaker_entry = pentry.get("speaker_id", {})
            speaker = speaker_entry.get("current", {}).get("value", "unknown")

            listener_entry = pentry.get("listener_id", {})
            listener = listener_entry.get("current", {}).get("value", "unknown")

            text_entry = pentry.get("promise_text", {})
            text = text_entry.get("current", {}).get("value", "")

            chapter_entry = pentry.get("chapter_made", {})
            chapter = chapter_entry.get("current", {}).get("value", "unknown")

            # Check if any active character is speaker (subject) or listener (object)
            if speaker in active_characters or listener in active_characters:
                has_promises = True
                xml_parts.append(
                    f"  <Promise speaker=\"{speaker}\" listener=\"{listener}\" status=\"{status}\" chapter_made=\"{chapter}\">\n"
                    f"    {text}\n"
                    f"  </Promise>"
                )

        if not has_promises:
            return ""

        xml_parts.append("</ActivePromises>")
        return "\n".join(xml_parts)
