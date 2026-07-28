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
        self._sentiment_analyzer = None  # Lazy-loaded VADER analyzer

    def _get_sentiment_analyzer(self):
        """Lazy-load the VADER sentiment analyzer (offline, bundled lexicon)."""
        if self._sentiment_analyzer is None:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._sentiment_analyzer = SentimentIntensityAnalyzer()
        return self._sentiment_analyzer

    def detect_scenes(self, text: str, chapter_num: int) -> list:
        """Detect scene boundaries within a chapter.

        Advanced Phase 12 implementation:
          - Split text into paragraphs (double-newline separators).
          - Detect visual break patterns (e.g. * * *, ---, ***) and start new scenes.
          - Detect headings (short uppercase/chapter lines).
          - Detect temporal and spatial transition sentences at the start of a paragraph
            (e.g., "The next morning,", "Three hours later,", "Back at the laboratory,").
        """
        import re

        scenes = []
        if not text or not text.strip():
            return scenes

        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        current_scene = None
        scene_idx = 0

        def _is_heading(p: str) -> bool:
            s = p.split('\n', 1)[0].strip()
            if len(s) <= 120 and (s.upper() == s or s.lower().startswith(("chapter", "prologue", "epilogue"))):
                return True
            return False

        def _is_visual_break(p: str) -> bool:
            # Matches patterns like * * *, ***, ---, ___
            cleaned = p.replace(" ", "")
            if len(cleaned) >= 3 and all(c in ('*', '-', '_') for c in cleaned):
                return True
            return False

        # Transition phrases indicating scene time/setting shift
        TRANSITION_PATTERN = re.compile(
            r"^(?:(?:the|a|several|many|two|three|four|five|next|following)\s+(?:day|morning|afternoon|evening|night|week|month|year|hour|minute|second)s?\s+(?:later|after|passed|had\s+passed|before)\b|"
            r"(?:the\s+next|the\s+following)\s+(?:day|morning|afternoon|evening|night|week|month|year)\b|"
            r"(?:later\s+that|early\s+the|by\s+the|during\s+the|at\s+the|in\s+the)\s+(?:day|morning|afternoon|evening|night|meanwhile|time)\b|"
            r"(?:meanwhile|meanwhile,|later,|afterward,|afterwards,|suddenly,|suddenly)\b|"
            r"(?:back\s+at|inside\s+the|across\s+the|upon\s+entering|when\s+they\s+arrived|outside\s+the)\s+[a-z]+)",
            re.IGNORECASE
        )

        def _has_scene_transition_phrase(p: str) -> bool:
            # Check the first sentence of the paragraph
            first_sentence = re.split(r'[.!?]', p)[0].strip()
            return bool(TRANSITION_PATTERN.match(first_sentence))

        for para in paragraphs:
            # If it's a visual break, we start a new scene and discard the separator line itself
            if _is_visual_break(para):
                if current_scene:
                    scenes.append(current_scene)
                    current_scene = None
                continue

            if _is_heading(para):
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
            elif _has_scene_transition_phrase(para) and current_scene is not None:
                # If there's a strong transition phrase, split here and start a new scene
                scene_idx += 1
                scenes.append(current_scene)
                current_scene = {
                    "id": f"ch{chapter_num}.sc{scene_idx}",
                    "title": f"Scene {scene_idx} - Setting Transition",
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
            scenes.append(current_scene)

        # Finalize scenes: join paragraph text
        for s in scenes:
            s["text"] = "\n\n".join(s.get("paragraphs", []))

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

        # Detect emotional tone — categorical keyword-bag label (mysterious, romantic,
        # etc.) kept as-is, since VADER can't distinguish those categories. Alongside it,
        # add a real quantitative polarity score (VADER compound, offline/lexicon-based)
        # so downstream consumers aren't limited to a single hand-picked keyword bucket.
        tone = self._detect_emotional_tone(scene_lower)
        analyzed["emotional_tone"] = tone
        analyzed["sentiment_compound"] = self._detect_sentiment_score(scene_text)

        # Detect outcome
        outcome = self._detect_scene_outcome(scene_text, scene_lower)
        analyzed["outcome"] = outcome

        # Detect POV character (Phase 12)
        pov = self._detect_scene_pov(scene_text, characters_present, chapter_data)
        analyzed["pov"] = pov

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

    def _detect_sentiment_score(self, scene_text: str) -> float:
        """Real polarity score for the scene (VADER compound, -1.0 to 1.0)."""
        if not scene_text or not scene_text.strip():
            return 0.0
        try:
            scores = self._get_sentiment_analyzer().polarity_scores(scene_text)
            return round(scores["compound"], 4)
        except Exception as e:
            logger.warning(f"VADER sentiment scoring unavailable for scene: {e}")
            return 0.0

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

    def _detect_scene_pov(self, scene_text: str, characters_present: List[str], chapter_data) -> str:
        """Detect the Point of View (POV) character for the scene."""
        if not characters_present:
            return "unknown"

        if len(characters_present) == 1:
            return characters_present[0]

        scores = {char: 0 for char in characters_present}
        scene_lower = scene_text.lower()

        # Count direct mentions of character names / aliases
        for char in characters_present:
            escaped_name = re.escape(char.lower())
            occurrences = len(re.findall(r"\b" + escaped_name + r"\b", scene_lower))
            scores[char] += occurrences * 2

        # Check coreference clusters to count resolved pronoun mentions
        if hasattr(chapter_data, "coreferences") and chapter_data.coreferences:
            for cluster in chapter_data.coreferences:
                canonical = cluster.canonical_mention.lower()
                matched_char = None
                for char in characters_present:
                    if char.lower() in canonical or canonical in char.lower():
                        matched_char = char
                        break

                if matched_char:
                    for mention in cluster.mentions:
                        if mention.lower() in scene_lower:
                            scores[matched_char] += 1

        best_char = max(scores, key=scores.get)
        if scores[best_char] > 0:
            return best_char
        return characters_present[0]

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
