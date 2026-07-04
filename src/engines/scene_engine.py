"""
Scene Engine — Scene boundary detection and analysis.

Implementation: Phase 8 (basic), Phase 12 (rich analysis)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set

logger = logging.getLogger("NarrativeEngine.Engines.Scene")


class SceneEngine:
    """Detects scene boundaries and extracts scene-level evidence."""

    def __init__(self, config=None):
        self._config = config

    def detect_scenes(self, text: str, chapter_num: int) -> list:
        """Detect scene boundaries within a chapter.

        Heuristic Phase 8 implementation:
          - Split text into paragraphs (double-newline separators).
          - Treat each paragraph as a candidate scene segment.
          - If a paragraph appears to be a heading (short, title-case or all-caps),
            start a new scene and attach following paragraphs until next heading.
          - Return a list of scene dicts with minimal metadata.
        """
        import re

        scenes = []
        if not text or not text.strip():
            return scenes

        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        current_scene = None
        scene_idx = 0

        def _is_heading(p: str) -> bool:
            # Heading heuristics: short line, mostly uppercase or starts with Chapter/Prologue
            s = p.split('\n', 1)[0].strip()
            if len(s) <= 120 and (s.upper() == s or s.lower().startswith(("chapter", "prologue", "epilogue"))):
                return True
            return False

        for para in paragraphs:
            if _is_heading(para):
                # Start a new scene with heading as title
                scene_idx += 1
                if current_scene:
                    scenes.append(current_scene)
                current_scene = {
                    "id": f"ch{chapter_num}.sc{scene_idx}",
                    "title": para.split('\n', 1)[0].strip(),
                    "text": "",
                    "chapter": chapter_num,
                    "paragraphs": [para],
                }
            else:
                if current_scene is None:
                    scene_idx += 1
                    current_scene = {
                        "id": f"ch{chapter_num}.sc{scene_idx}",
                        "title": None,
                        "text": "",
                        "chapter": chapter_num,
                        "paragraphs": [para],
                    }
                else:
                    current_scene["paragraphs"].append(para)

        if current_scene:
            # Finalize scenes: join paragraph text
            for s in scenes:
                s["text"] = "\n\n".join(s.get("paragraphs", []))
            current_scene["text"] = "\n\n".join(current_scene.get("paragraphs", []))
            scenes.append(current_scene)

        return scenes

    def analyze_scene_richness(
        self,
        scene: Dict,
        chapter_data,
        character_names: Set[str],
    ) -> Dict:
        """
        Perform rich scene analysis (Phase 12).

        Analyzes:
        - Scene purpose (what the scene accomplishes)
        - Conflict (central tension or problem)
        - Characters present
        - Emotional tone
        - Outcome (resolution state)
        """
        scene_text = scene.get("text", "")
        scene_lower = scene_text.lower()

        analyzed = scene.copy()

        # Detect characters present in scene
        characters_present = self._detect_characters_in_scene(scene_text, character_names)
        analyzed["characters_present"] = characters_present

        # Detect scene purpose
        purpose = self._detect_scene_purpose(scene_text, scene_lower)
        analyzed["purpose"] = purpose

        # Detect conflict
        conflict = self._detect_scene_conflict(scene_text, scene_lower)
        analyzed["conflict"] = conflict

        # Detect emotional tone
        tone = self._detect_emotional_tone(scene_lower)
        analyzed["emotional_tone"] = tone

        # Detect outcome
        outcome = self._detect_scene_outcome(scene_text, scene_lower)
        analyzed["outcome"] = outcome

        return analyzed

    def _detect_characters_in_scene(self, scene_text: str, character_names: Set[str]) -> List[str]:
        """Detect which characters are present in the scene."""
        present = []
        scene_lower = scene_text.lower()

        for name in character_names:
            if name.lower() in scene_lower:
                present.append(name)

        return present

    def _detect_scene_purpose(self, scene_text: str, scene_lower: str) -> str:
        """Detect the purpose of the scene based on content."""
        purpose_keywords = {
            "exposition": ["introduced", "background", "explained", "history", "origin"],
            "character_development": ["felt", "thought", "realized", "understood", "changed"],
            "plot_advancement": ["decided", "began", "started", "embarked", "journey"],
            "conflict": ["argued", "fought", "confronted", "challenged", "opposed"],
            "climax": ["final", "ultimate", "decisive", "conclusion", "end"],
            "resolution": ["resolved", "settled", "concluded", "finished", "ended"],
            "transition": ["moved", "traveled", "arrived", "departed", "left"],
        }

        purpose_scores = {}
        for purpose, keywords in purpose_keywords.items():
            score = sum(1 for keyword in keywords if keyword in scene_lower)
            if score > 0:
                purpose_scores[purpose] = score

        if purpose_scores:
            return max(purpose_scores, key=purpose_scores.get)
        return "unknown"

    def _detect_scene_conflict(self, scene_text: str, scene_lower: str) -> str:
        """Detect the central conflict of the scene."""
        conflict_keywords = {
            "internal": ["struggled with", "wondered", "doubted", "feared", "hesitated"],
            "interpersonal": ["argued", "fought", "disagreed", "confronted", "accused"],
            "external": ["attacked", "chased", "blocked", "prevented", "obstacle"],
            "societal": ["against", "rebelled", "protested", "opposed", "resisted"],
            "nature": ["storm", "weather", "wilderness", "survived", "endured"],
        }

        conflict_scores = {}
        for conflict_type, keywords in conflict_keywords.items():
            score = sum(1 for keyword in keywords if keyword in scene_lower)
            if score > 0:
                conflict_scores[conflict_type] = score

        if conflict_scores:
            return max(conflict_scores, key=conflict_scores.get)
        return "none"

    def _detect_emotional_tone(self, scene_lower: str) -> str:
        """Detect the emotional tone of the scene."""
        tone_keywords = {
            "tense": ["tense", "nervous", "anxious", "worried", "afraid"],
            "sad": ["sad", "sorrowful", "grief", "mournful", "melancholy"],
            "joyful": ["happy", "joyful", "cheerful", "delighted", "celebrated"],
            "angry": ["angry", "furious", "rage", "irritated", "annoyed"],
            "hopeful": ["hope", "optimistic", "expectant", "confident", "believed"],
            "mysterious": ["mysterious", "strange", "unknown", "puzzling", "secret"],
            "peaceful": ["peaceful", "calm", "serene", "tranquil", "quiet"],
            "romantic": ["love", "romance", "passion", "affection", "devotion"],
        }

        tone_scores = {}
        for tone, keywords in tone_keywords.items():
            score = sum(1 for keyword in keywords if keyword in scene_lower)
            if score > 0:
                tone_scores[tone] = score

        if tone_scores:
            return max(tone_scores, key=tone_scores.get)
        return "neutral"

    def _detect_scene_outcome(self, scene_text: str, scene_lower: str) -> str:
        """Detect the outcome/resolution state of the scene."""
        outcome_keywords = {
            "success": ["succeeded", "succeeded in", "accomplished", "achieved", "won", "victory"],
            "failure": ["failed", "lost", "defeated", "failed to", "couldn't"],
            "partial": ["partially", "somewhat", "incomplete", "unfinished"],
            "ongoing": ["continued", "remained", "stayed", "persisted"],
            "unknown": ["unclear", "uncertain", "not sure", "didn't know"],
        }

        outcome_scores = {}
        for outcome, keywords in outcome_keywords.items():
            score = sum(1 for keyword in keywords if keyword in scene_lower)
            if score > 0:
                outcome_scores[outcome] = score

        if outcome_scores:
            return max(outcome_scores, key=outcome_scores.get)
        return "neutral"

    def analyze_all_scenes(
        self,
        scenes: List[Dict],
        chapter_data,
        character_names: Set[str],
    ) -> List[Dict]:
        """Analyze all scenes in a chapter with rich metadata."""
        analyzed_scenes = []
        for scene in scenes:
            analyzed = self.analyze_scene_richness(scene, chapter_data, character_names)
            analyzed_scenes.append(analyzed)
        return analyzed_scenes
