import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional

logger = logging.getLogger("NarrativeEngine.Pipeline.ContextRetriever")

class ContextRetriever:
    """
    RAG Context Preprocessing Pipeline, built around a single source of truth.
    Stage 1: Boundary-Safe Entity and Location Scanner.
    Stage 2: Four-Tier Surgical State Hydration (Characters, Relationships, Promises, World).
    Stage 3: Token-budgeted XML Context Compilation.

    Data source: the canonical NarrativeState — either the live in-memory object
    (the normal case: the caller already has it) or, only if none is provided,
    the canonical narrative_state.json file on disk (cold start / standalone use).
    No other file is ever read. A prior version of this class tried up to nine
    different files — narrative_state.json, three separate legacy top-level JSON
    files, and four data/{profiles,relationships,promises,clues} folders — and
    merged whatever partial, possibly-stale data each happened to contain, with
    no way to tell which source actually won for a given field.
    """

    def __init__(self, config=None):
        self._config = config
        self._memory_dir = Path("data/memory")
        if config and hasattr(config, "memory_dir"):
            self._memory_dir = Path(config.memory_dir)

    def retrieve_context(self, raw_text: str, current_state: Optional[Any] = None) -> Tuple[Optional[str], List[str]]:
        """
        Runs entity pre-scans, hydrates data structures, compiles budgeted XML block.

        Args:
            raw_text: The incoming chapter text to scan for active entities.
            current_state: The live NarrativeState, if the caller has one (Pipeline
                always does). When omitted, falls back to reading the canonical
                narrative_state.json from disk — the only supported fallback.

        Returns a tuple: (context_block_str, list_of_active_character_ids)
        """
        data_sources = self._load_data_sources(current_state)
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
            world_data=world_data,
            threats_data=data_sources.get("threats", {}),
            themes_data=data_sources.get("themes", {}),
            motifs_data=data_sources.get("motifs", {}),
            chapter_summaries_data=data_sources.get("chapter_summaries", {}),
            timeline_data=data_sources.get("timeline", []),
        )

        return context_str, sorted(list(active_characters))

    def _load_data_sources(self, current_state: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
        """
        Single source of truth, with exactly one explicit fallback.

        If the caller already has a live NarrativeState (the normal case — Pipeline
        always does), use it directly: no disk read at all, and no risk of the
        in-memory state and an on-disk snapshot disagreeing. Only when no state
        object is provided (cold start, or a caller that genuinely doesn't have
        one yet) does this read the canonical narrative_state.json — and if that
        doesn't exist or fails to parse, it returns empty structures rather than
        guessing from some other file.
        """
        if current_state is not None:
            return self._extract_sources(current_state.to_dict())

        state_path = self._memory_dir / "narrative_state.json"
        if not state_path.exists():
            logger.info("No canonical narrative_state.json found yet (cold start). No context to retrieve.")
            return self._empty_data_sources()

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                sdata = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Canonical narrative_state.json exists but could not be read/parsed: {e}")
            return self._empty_data_sources()

        return self._extract_sources(sdata)

    def _extract_sources(self, sdata: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {
            "characters": sdata.get("characters", {}),
            "relationships": sdata.get("relationships", {}),
            "promises": sdata.get("promises", {}),
            "world": sdata.get("world", {}),
            "threats": sdata.get("threats", {}),
            "themes": sdata.get("themes", {}),
            "motifs": sdata.get("motifs", {}),
            "chapter_summaries": sdata.get("chapter_summaries", {}),
            "timeline": sdata.get("timeline", []),
        }

    def _empty_data_sources(self) -> Dict[str, Dict[str, Any]]:
        return {
            "characters": {}, "relationships": {}, "promises": {}, "world": {},
            "threats": {}, "themes": {}, "motifs": {}, "chapter_summaries": {},
            "timeline": [],
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
        world_data: Dict[str, Any],
        threats_data: Dict[str, Any],
        themes_data: Dict[str, Any],
        motifs_data: Dict[str, Any],
        chapter_summaries_data: Dict[str, Any],
        timeline_data: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Hydrates Tiers and compiles them into a token-budgeted XML structure.
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

        # Tier E: Threats XML Parts
        threat_xmls = []
        for tid, tentry in sorted(threats_data.items()):
            if not isinstance(tentry, dict): continue
            status = tentry.get("status", {}).get("current", {}).get("value", "ACTIVE")
            if status not in ("ACTIVE", "unresolved"): continue
            source = tentry.get("source_id", {}).get("current", {}).get("value", "unknown")
            target = tentry.get("target_id", {}).get("current", {}).get("value", "unknown")
            if source in active_characters or target in active_characters:
                text = tentry.get("threat_text", {}).get("current", {}).get("value", "")
                chapter = tentry.get("chapter_made", {}).get("current", {}).get("value", "unknown")
                threat_xmls.append(
                    f"    <Threat source=\"{source}\" target=\"{target}\" status=\"{status}\" chapter_made=\"{chapter}\">\n"
                    f"      {str(text).strip()}\n"
                    f"    </Threat>"
                )

        # Tier F & G: Themes and Motifs
        theme_xmls = []
        for thid, thentry in sorted(themes_data.items()):
            if not isinstance(thentry, dict): continue
            desc = thentry.get("description", {}).get("current", {}).get("value", "")
            theme_xmls.append(f"    <Theme id=\"{thid}\">{str(desc).strip()}</Theme>")
            
        motif_xmls = []
        for mid, mentry in sorted(motifs_data.items()):
            if not isinstance(mentry, dict): continue
            desc = mentry.get("description", {}).get("current", {}).get("value", "")
            motif_xmls.append(f"    <Motif id=\"{mid}\">{str(desc).strip()}</Motif>")

        # Tier H: Chapter Summaries
        summary_xmls = []
        for ch_num, summ in sorted(chapter_summaries_data.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
            summary_xmls.append(f"    <Summary chapter=\"{ch_num}\">{str(summ).strip()}</Summary>")

        # Tier I: Recent Timeline — the last 15 recorded events, so every LLM call (extraction
        # stages and editorial critique alike) has some cross-chapter continuity beyond just
        # chapter summaries: what actually just happened, in what order. Capped by count rather
        # than folded into the byte-budget accounting below, since it's naturally small and a
        # fixed cap is simpler to reason about than adding a fourth thing fighting for the same
        # budget.
        timeline_xmls = []
        for event in (timeline_data or [])[-15:]:
            subject = event.get("subject") or "?"
            predicate = event.get("predicate") or "?"
            obj = event.get("object") or ""
            chapter = event.get("chapter")
            timeline_xmls.append(f"    <Event chapter=\"{chapter}\">{subject} {predicate} {obj}</Event>".rstrip())

        # Stage 3: Token budget XML assembly
        # XML tags layout size overhead
        wrapper_start = "<StoryContext>\n"
        char_start, char_end = "  <ActiveCharacters>\n", "  </ActiveCharacters>\n"
        clue_start, clue_end = "  <SceneClues>\n", "  </SceneClues>\n"
        rel_start, rel_end = "  <ActiveRelationships>\n", "  </ActiveRelationships>\n"
        prom_start, prom_end = "  <OpenPromises>\n", "  </OpenPromises>\n"
        threat_start, threat_end = "  <ActiveThreats>\n", "  </ActiveThreats>\n"
        theme_start, theme_end = "  <CoreThemes>\n", "  </CoreThemes>\n"
        motif_start, motif_end = "  <CoreMotifs>\n", "  </CoreMotifs>\n"
        summ_start, summ_end = "  <ChapterSummaries>\n", "  </ChapterSummaries>\n"
        timeline_start, timeline_end = "  <RecentTimeline>\n", "  </RecentTimeline>\n"
        wrapper_end = "</StoryContext>"

        # Compile Tiers A & D (Characters & Clues)
        chars_xml_str = "\n".join(char_xmls)
        clues_xml_str = "\n".join(clue_xmls)

        current_xml = wrapper_start
        if char_xmls: current_xml += char_start + chars_xml_str + "\n" + char_end
        if clue_xmls: current_xml += clue_start + clues_xml_str + "\n" + clue_end
        if theme_xmls: current_xml += theme_start + "\n".join(theme_xmls) + "\n" + theme_end
        if motif_xmls: current_xml += motif_start + "\n".join(motif_xmls) + "\n" + motif_end
        if summary_xmls: current_xml += summ_start + "\n".join(summary_xmls) + "\n" + summ_end
        if timeline_xmls: current_xml += timeline_start + "\n".join(timeline_xmls) + "\n" + timeline_end

        # Calculate budget for Relationships, Promises, Threats
        budget = 6000 - len(current_xml) - len(wrapper_end) - 200 # Add buffer

        included_rels = []
        included_proms = []
        included_threats = []

        if budget > 0:
            for rel in relationship_xmls:
                if len(rel) + len(rel_start) + len(rel_end) < budget:
                    included_rels.append(rel)
                    budget -= len(rel)
            
            for prom in promise_xmls:
                if len(prom) + len(prom_start) + len(prom_end) < budget:
                    included_proms.append(prom)
                    budget -= len(prom)

            for threat in threat_xmls:
                if len(threat) + len(threat_start) + len(threat_end) < budget:
                    included_threats.append(threat)
                    budget -= len(threat)

        # Build final budgeted XML block
        if included_rels: current_xml += rel_start + "\n".join(included_rels) + "\n" + rel_end
        if included_proms: current_xml += prom_start + "\n".join(included_proms) + "\n" + prom_end
        if included_threats: current_xml += threat_start + "\n".join(included_threats) + "\n" + threat_end

        current_xml += wrapper_end
        return current_xml
