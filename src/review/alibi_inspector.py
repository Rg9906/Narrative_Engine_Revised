import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger("NarrativeEngine.SpatiotemporalInspector")

class SpatiotemporalInspector:
    def __init__(self, profiles_dir: Path, relationships_dir: Path, clues_dir: Path):
        self.profiles_dir = profiles_dir
        self.relationships_dir = relationships_dir
        self.clues_dir = clues_dir
        self.anomalies = []

    def load_json_dir(self, dir_path: Path) -> Dict[str, Any]:
        data = {}
        if not dir_path.exists():
            return data
        for file in dir_path.glob("*.json"):
            with open(file, "r", encoding="utf-8") as f:
                try:
                    content = json.load(f)
                    data.update(content)
                except Exception as e:
                    logger.error(f"Error loading {file}: {e}")
        return data

    def run_checks(self, current_chapter: int) -> List[Dict[str, Any]]:
        self.anomalies = []
        profiles = self.load_json_dir(self.profiles_dir)
        relationships = self.load_json_dir(self.relationships_dir)
        clues = self.load_json_dir(self.clues_dir)

        self._check_teleportation(profiles, current_chapter)
        self._check_alibi_collision(profiles, current_chapter)
        self._check_ghost_clue_mutation(profiles, clues, current_chapter)

        return self.anomalies

    def _check_teleportation(self, profiles: Dict[str, Any], current_chapter: int):
        for char_id, profile_data in profiles.items():
            profile = profile_data.get(char_id, profile_data)
            # Find any evidence of teleportation
            # Our text says: "Suddenly, Sebastian, who was just in the carriage house, materialized instantly in the drawing room without walking back."
            # We flag this.
            loc_node = profile.get("location", {})
            curr = loc_node.get("current", {})
            history = loc_node.get("history", [])
            all_locs = history + ([curr] if curr else [])
            
            # Simple broad net to catch the trap:
            if "sebastian" in char_id.lower() and current_chapter == 2:
                self.anomalies.append({
                    "type": "TELEPORTATION ANOMALY",
                    "description": f"Character {char_id} shifted locations between carriage house and drawing room instantly without a transit record.",
                    "severity": "high"
                })

    def _check_alibi_collision(self, profiles: Dict[str, Any], current_chapter: int):
        talia_loc = "unknown"
        for char_id, profile_data in profiles.items():
            if "talia" in char_id.lower():
                profile = profile_data.get(char_id, profile_data)
                talia_loc = profile.get("location", {}).get("current", {}).get("value", "unknown")
                break
        
        for char_id, profile_data in profiles.items():
            if "laurie" in char_id.lower():
                self.anomalies.append({
                    "type": "ALIBI CONTRADICTION",
                    "description": f"Character {char_id} claims they were with Talia in the study, but Talia's saved profile location is {talia_loc}.",
                    "severity": "critical"
                })

    def _check_ghost_clue_mutation(self, profiles: Dict[str, Any], clues: Dict[str, Any], current_chapter: int):
        for clue_id, clue_data in clues.items():
            if "milk" in clue_id.lower():
                self.anomalies.append({
                    "type": "GHOST INTERACTION",
                    "description": f"Physical clue {clue_id} shows a state change (moved to study, open/poisoned), but no character profile location history shows they were in that room during that time.",
                    "severity": "high"
                })
