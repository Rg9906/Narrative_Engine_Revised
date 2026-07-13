"""
Character Memory — Evolving character state.

Tracks character profiles with versioned history:
  - Identity (names, aliases)
  - Physical traits
  - Personality traits
  - Emotional state (evolving)
  - Goals, fears, motivations
  - Arc progression

Implementation: Phase 6 (basic), Phase 9 (advanced)
"""

import re
from typing import Dict, List, Optional, Tuple, Set

from src.memory.base_memory import BaseMemory
from src.models.state import (
    ChapterData,
    Evidence,
    ExtractedDialogue,
    ExtractedEntity,
    ExtractedRelation,
    NarrativeElementType,
    StateChange,
    StateChangeType,
)


class CharacterMemory(BaseMemory):
    """Manages evolving character state with full history and evidence."""

    PRONOUNS = {
        "i", "me", "you", "he", "him", "she", "her", "they", "them",
        "we", "us", "it", "its", "his", "hers", "their", "theirs",
    }

    # Physical trait keywords (Phase 9)
    PHYSICAL_TRAIT_KEYWORDS = {
        "hair_color": ["hair", "blonde", "brunette", "red", "black", "brown", "gray", "white", "blond"],
        "eye_color": ["eyes", "blue", "green", "brown", "hazel", "gray", "dark", "light"],
        "height": ["tall", "short", "height", "towering", "petite", "lanky"],
        "build": ["thin", "slender", "stocky", "muscular", "athletic", "heavy", "lean"],
        "age": ["young", "old", "age", "years old", "teenage", "middle-aged", "elderly"],
        "distinctive": ["scar", "tattoo", "limp", "freckles", "glasses", "beard", "mustache"],
    }

    # Personality trait keywords (Phase 9)
    PERSONALITY_KEYWORDS = {
        "brave": ["brave", "courageous", "fearless", "bold", "daring"],
        "shy": ["shy", "timid", "reserved", "quiet", "withdrawn"],
        "kind": ["kind", "gentle", "compassionate", "caring", "warm"],
        "cruel": ["cruel", "ruthless", "mean", "harsh", "cold"],
        "intelligent": ["smart", "intelligent", "clever", "wise", "brilliant"],
        "stubborn": ["stubborn", "obstinate", "headstrong", "willful"],
        "ambitious": ["ambitious", "driven", "determined", "goal-oriented"],
        "loyal": ["loyal", "faithful", "devoted", "trustworthy"],
        "deceptive": ["deceptive", "dishonest", "cunning", "sly", "manipulative"],
        "humorous": ["funny", "witty", "humorous", "sarcastic", "playful"],
    }

    # Emotion keywords (Phase 9)
    EMOTION_KEYWORDS = {
        "happy": ["happy", "joyful", "cheerful", "delighted", "pleased", "glad"],
        "sad": ["sad", "unhappy", "sorrowful", "melancholy", "depressed", "grief"],
        "angry": ["angry", "furious", "rage", "irritated", "annoyed", "mad"],
        "afraid": ["afraid", "fearful", "terrified", "scared", "anxious", "worried"],
        "surprised": ["surprised", "shocked", "astonished", "amazed", "stunned"],
        "disgusted": ["disgusted", "revolted", "repulsed", "sickened"],
        "hopeful": ["hopeful", "optimistic", "expectant", "confident"],
        "guilty": ["guilty", "ashamed", "remorseful", "regretful"],
        "proud": ["proud", "confident", "accomplished", "triumphant"],
        "lonely": ["lonely", "isolated", "alone", "solitary"],
    }

    # Goal/action keywords (Phase 9)
    GOAL_INDICATORS = ["want to", "need to", "must", "have to", "trying to", "attempting to", "seeking", "searching for", "looking for", "goal", "aim", "purpose"]

    # Fear keywords (Phase 9)
    FEAR_INDICATORS = ["fear", "afraid of", "terrified of", "scared of", "dread", "phobia", "worried about"]

    # Arc stage keywords (Phase 9)
    ARC_STAGES = {
        "introduction": ["introduced", "first appeared", "met", "arrived"],
        "inciting_incident": ["received call", "discovered", "learned", "found out"],
        "rising_action": ["journey", "pursued", "chased", "fought", "struggled"],
        "crisis": ["confronted", "faced", "challenged", "tested"],
        "climax": ["final battle", "confrontation", "showdown", "ultimate test"],
        "resolution": ["succeeded", "failed", "resolved", "concluded", "returned"],
    }

    def __init__(self, memory_file=None, existing_entries: Optional[Dict[str, Dict[str, object]]] = None):
        super().__init__(memory_file)
        if existing_entries is not None:
            self._entries = existing_entries

    def load_entries(self, entries: Dict[str, Dict[str, object]]) -> None:
        """Load existing character entries into the memory helper."""
        if entries is not None:
            self._entries = entries

    def update_from_chapter(self, chapter_data: ChapterData, chapter_num: int) -> List[StateChange]:
        """
        Update character state from chapter evidence.

        This interprets raw evidence (entities, dialogue, actions) into
        meaningful character state transitions.

        Returns:
            List of StateChange objects describing what changed.
        """
        changes: List[StateChange] = []
        coref_map = self._build_coref_map(chapter_data)
        mentions = self._collect_character_mentions(chapter_data, coref_map)

        for mention_text in mentions:
            char_id = self.resolve_character_id(mention_text, self._entries)
            if not char_id:
                continue

            alias = mention_text.strip()
            canonical_name = alias
            existing_entity = self.get_entity_state(char_id)
            introduction = existing_entity is None

            # Update canonical name if this is the first mention.
            if introduction:
                self.update_entry(
                    char_id,
                    "canonical_name",
                    canonical_name,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="First observed mention of character.",
                    importance=0.9,
                )
                self.update_entry(
                    char_id,
                    "aliases",
                    [canonical_name],
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="Initial alias list created from first mention.",
                )
                self.update_entry(
                    char_id,
                    "last_seen_chapter",
                    chapter_num,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="Character seen in current chapter.",
                )
                self.update_entry(
                    char_id,
                    "mention_count",
                    1,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=1.0,
                    reasoning="First mention observed this chapter.",
                )
                changes.append(
                    StateChange(
                        change_type=StateChangeType.INTRODUCTION,
                        target_type=NarrativeElementType.CHARACTER,
                        target_id=char_id,
                        field_key="canonical_name",
                        new_value=canonical_name,
                        confidence=1.0,
                        reasoning="New character introduced from chapter evidence.",
                    )
                )
                continue

            # Existing character: update alias list if needed.
            alias_entry = self.get_entry(char_id, "aliases")
            if alias_entry and alias not in alias_entry.current.value:
                new_aliases = list(alias_entry.current.value) + [alias]
                self.update_entry(
                    char_id,
                    "aliases",
                    new_aliases,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.85,
                    reasoning="New alias observed for existing character.",
                )
                changes.append(
                    StateChange(
                        change_type=StateChangeType.EVOLUTION,
                        target_type=NarrativeElementType.CHARACTER,
                        target_id=char_id,
                        field_key="aliases",
                        old_value=alias_entry.current.value,
                        new_value=new_aliases,
                        confidence=0.85,
                        reasoning="Alias list expanded from chapter evidence.",
                    )
                )

            # Always refresh last seen and mention count for existing characters.
            last_seen_entry = self.get_entry(char_id, "last_seen_chapter")
            if last_seen_entry is None or last_seen_entry.current.value != chapter_num:
                self.update_entry(
                    char_id,
                    "last_seen_chapter",
                    chapter_num,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.9,
                    reasoning="Character observed in current chapter.",
                )

            mention_count_entry = self.get_entry(char_id, "mention_count")
            previous_count = mention_count_entry.current.value if mention_count_entry and mention_count_entry.current else 0
            new_count = previous_count + 1
            self.update_entry(
                char_id,
                "mention_count",
                new_count,
                chapter=chapter_num,
                evidence_ids=[],
                confidence=0.9,
                reasoning="Mention count incremented for observed character.",
            )
            changes.append(
                StateChange(
                    change_type=StateChangeType.CONFIRMATION,
                    target_type=NarrativeElementType.CHARACTER,
                    target_id=char_id,
                    field_key="mention_count",
                    old_value=previous_count,
                    new_value=new_count,
                    confidence=0.9,
                    reasoning="Existing character mention confirmed and tracked.",
                )
            )

        return changes

    def extract_advanced_attributes(
        self,
        chapter_data: ChapterData,
        chapter_num: int,
    ) -> List[StateChange]:
        """
        Extract advanced character attributes from chapter text (Phase 9).

        This analyzes the raw text and dialogue to extract:
        - Physical traits (appearance, age, distinctive features)
        - Personality traits
        - Emotional state
        - Goals and motivations
        - Fears
        - Arc progression indicators

        Returns:
            List of StateChange objects for advanced attributes.
        """
        changes: List[StateChange] = []
        coref_map = self._build_coref_map(chapter_data)

        # Process each character mention in the chapter
        for char_id in self._entries.keys():
            char_state = self.get_entity_state(char_id)
            if not char_state:
                continue

            canonical_name = char_state.get("canonical_name")
            if not canonical_name or not canonical_name.current:
                continue

            name_variants = self._get_name_variants(canonical_name.current.value, char_state)

            # Extract physical traits from text
            physical_changes = self._extract_physical_traits(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(physical_changes)

            # Extract personality traits
            personality_changes = self._extract_personality_traits(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(personality_changes)

            # Extract emotional state
            emotion_changes = self._extract_emotional_state(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(emotion_changes)

            # Extract goals
            goal_changes = self._extract_goals(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(goal_changes)

            # Extract fears
            fear_changes = self._extract_fears(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(fear_changes)

            # Update arc stage
            arc_changes = self._update_arc_stage(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(arc_changes)

            # Extract inventory items
            inventory_changes = self._extract_inventory(
                chapter_data, char_id, name_variants, chapter_num, coref_map
            )
            changes.extend(inventory_changes)

        return changes

    def _get_name_variants(self, canonical_name: str, char_state: Dict) -> Set[str]:
        """Get all known name variants for a character."""
        variants = {canonical_name.lower()}
        alias_entry = char_state.get("aliases")
        if alias_entry and alias_entry.current:
            for alias in alias_entry.current.value:
                variants.add(alias.lower())
        return variants

    def _extract_physical_traits(
        self,
        chapter_data: ChapterData,
        char_id: str,
        name_variants: Set[str],
        chapter_num: int,
        coref_map: Dict[str, str],
    ) -> List[StateChange]:
        """Extract physical traits from text mentioning the character."""
        changes: List[StateChange] = []
        text = chapter_data.raw_text.lower()

        for trait_type, keywords in self.PHYSICAL_TRAIT_KEYWORDS.items():
            for keyword in keywords:
                # Look for sentences containing character name and trait keyword
                sentences = chapter_data.sentences
                for sentence in sentences:
                    sentence_lower = sentence.lower()
                    if any(variant in sentence_lower for variant in name_variants):
                        if keyword in sentence_lower:
                            # Extract the specific trait value
                            trait_value = self._extract_trait_value(sentence, keyword, trait_type)
                            if trait_value:
                                existing = self.get_entry(char_id, f"physical_{trait_type}")
                                old_value = existing.current.value if existing and existing.current else None

                                if old_value != trait_value:
                                    self.update_entry(
                                        char_id,
                                        f"physical_{trait_type}",
                                        trait_value,
                                        chapter=chapter_num,
                                        evidence_ids=[],
                                        confidence=0.7,
                                        reasoning=f"Extracted from sentence: '{sentence[:100]}...'",
                                        importance=0.6,
                                    )
                                    changes.append(
                                        StateChange(
                                            change_type=StateChangeType.EVOLUTION if old_value else StateChangeType.INTRODUCTION,
                                            target_type=NarrativeElementType.CHARACTER,
                                            target_id=char_id,
                                            field_key=f"physical_{trait_type}",
                                            old_value=old_value,
                                            new_value=trait_value,
                                            confidence=0.7,
                                            reasoning=f"Physical trait extracted from text.",
                                        )
                                    )
        return changes

    def _extract_trait_value(self, sentence: str, keyword: str, trait_type: str) -> Optional[str]:
        """Extract the specific value of a trait from a sentence."""
        words = sentence.lower().split()
        if keyword not in words:
            return None

        # Simple extraction: return the word before or after the keyword
        keyword_idx = words.index(keyword)
        if keyword_idx > 0:
            return words[keyword_idx - 1]
        elif keyword_idx < len(words) - 1:
            return words[keyword_idx + 1]
        return keyword

    def _extract_personality_traits(
        self,
        chapter_data: ChapterData,
        char_id: str,
        name_variants: Set[str],
        chapter_num: int,
        coref_map: Dict[str, str],
    ) -> List[StateChange]:
        """Extract personality traits from text and dialogue."""
        changes: List[StateChange] = []

        for trait, keywords in self.PERSONALITY_KEYWORDS.items():
            # Check in dialogue
            for dialogue in chapter_data.dialogues:
                if dialogue.speaker and dialogue.speaker.lower() in name_variants:
                    dialogue_lower = dialogue.text.lower()
                    for keyword in keywords:
                        if keyword in dialogue_lower:
                            existing_traits = self.get_entry(char_id, "personality_traits")
                            current_traits = existing_traits.current.value if existing_traits and existing_traits.current else []

                            if trait not in current_traits:
                                new_traits = current_traits + [trait]
                                self.update_entry(
                                    char_id,
                                    "personality_traits",
                                    new_traits,
                                    chapter=chapter_num,
                                    evidence_ids=[],
                                    confidence=0.65,
                                    reasoning=f"Personality trait '{trait}' inferred from dialogue.",
                                    importance=0.7,
                                )
                                changes.append(
                                    StateChange(
                                        change_type=StateChangeType.EVOLUTION,
                                        target_type=NarrativeElementType.CHARACTER,
                                        target_id=char_id,
                                        field_key="personality_traits",
                                        old_value=current_traits,
                                        new_value=new_traits,
                                        confidence=0.65,
                                        reasoning=f"Personality trait extracted from dialogue.",
                                    )
                                )

            # Check in narration
            for sentence in chapter_data.sentences:
                sentence_lower = sentence.lower()
                if any(variant in sentence_lower for variant in name_variants):
                    for keyword in keywords:
                        if keyword in sentence_lower:
                            existing_traits = self.get_entry(char_id, "personality_traits")
                            current_traits = existing_traits.current.value if existing_traits and existing_traits.current else []

                            if trait not in current_traits:
                                new_traits = current_traits + [trait]
                                self.update_entry(
                                    char_id,
                                    "personality_traits",
                                    new_traits,
                                    chapter=chapter_num,
                                    evidence_ids=[],
                                    confidence=0.6,
                                    reasoning=f"Personality trait '{trait}' inferred from narration.",
                                    importance=0.7,
                                )
                                changes.append(
                                    StateChange(
                                        change_type=StateChangeType.EVOLUTION,
                                        target_type=NarrativeElementType.CHARACTER,
                                        target_id=char_id,
                                        field_key="personality_traits",
                                        old_value=current_traits,
                                        new_value=new_traits,
                                        confidence=0.6,
                                        reasoning=f"Personality trait extracted from narration.",
                                    )
                                )

        return changes

    def _extract_emotional_state(
        self,
        chapter_data: ChapterData,
        char_id: str,
        name_variants: Set[str],
        chapter_num: int,
        coref_map: Dict[str, str],
    ) -> List[StateChange]:
        """Extract current emotional state from text and dialogue."""
        changes: List[StateChange] = []
        detected_emotions = []

        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            # Check dialogue
            for dialogue in chapter_data.dialogues:
                if dialogue.speaker and dialogue.speaker.lower() in name_variants:
                    dialogue_lower = dialogue.text.lower()
                    for keyword in keywords:
                        if keyword in dialogue_lower:
                            detected_emotions.append(emotion)
                            break

            # Check narration
            for sentence in chapter_data.sentences:
                sentence_lower = sentence.lower()
                if any(variant in sentence_lower for variant in name_variants):
                    for keyword in keywords:
                        if keyword in sentence_lower:
                            detected_emotions.append(emotion)
                            break

        if detected_emotions:
            # Use the most frequently detected emotion
            from collections import Counter
            emotion_counts = Counter(detected_emotions)
            primary_emotion = emotion_counts.most_common(1)[0][0]

            existing_emotion = self.get_entry(char_id, "emotional_state")
            old_emotion = existing_emotion.current.value if existing_emotion and existing_emotion.current else None

            if old_emotion != primary_emotion:
                self.update_entry(
                    char_id,
                    "emotional_state",
                    primary_emotion,
                    chapter=chapter_num,
                    evidence_ids=[],
                    confidence=0.7,
                    reasoning=f"Emotional state inferred from text and dialogue.",
                    importance=0.8,
                )
                changes.append(
                    StateChange(
                        change_type=StateChangeType.EVOLUTION,
                        target_type=NarrativeElementType.CHARACTER,
                        target_id=char_id,
                        field_key="emotional_state",
                        old_value=old_emotion,
                        new_value=primary_emotion,
                        confidence=0.7,
                        reasoning=f"Emotional state changed based on chapter evidence.",
                    )
                )

        return changes

    def _extract_goals(
        self,
        chapter_data: ChapterData,
        char_id: str,
        name_variants: Set[str],
        chapter_num: int,
        coref_map: Dict[str, str],
    ) -> List[StateChange]:
        """Extract character goals from dialogue and narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()
            if any(variant in sentence_lower for variant in name_variants):
                for indicator in self.GOAL_INDICATORS:
                    if indicator in sentence_lower:
                        # Extract the goal (simplified: take words after indicator)
                        goal_text = sentence.strip()
                        existing_goals = self.get_entry(char_id, "goals")
                        current_goals = existing_goals.current.value if existing_goals and existing_goals.current else []

                        if goal_text not in current_goals:
                            new_goals = current_goals + [goal_text]
                            self.update_entry(
                                char_id,
                                "goals",
                                new_goals,
                                chapter=chapter_num,
                                evidence_ids=[],
                                confidence=0.6,
                                reasoning=f"Goal extracted from text containing '{indicator}'.",
                                importance=0.9,
                            )
                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.EVOLUTION,
                                    target_type=NarrativeElementType.CHARACTER,
                                    target_id=char_id,
                                    field_key="goals",
                                    old_value=current_goals,
                                    new_value=new_goals,
                                    confidence=0.6,
                                    reasoning=f"New goal identified from chapter text.",
                                )
                            )
                        break

        return changes

    def _extract_fears(
        self,
        chapter_data: ChapterData,
        char_id: str,
        name_variants: Set[str],
        chapter_num: int,
        coref_map: Dict[str, str],
    ) -> List[StateChange]:
        """Extract character fears from dialogue and narration."""
        changes: List[StateChange] = []

        for sentence in chapter_data.sentences:
            sentence_lower = sentence.lower()
            if any(variant in sentence_lower for variant in name_variants):
                for indicator in self.FEAR_INDICATORS:
                    if indicator in sentence_lower:
                        # Extract the fear (simplified: take the sentence)
                        fear_text = sentence.strip()
                        existing_fears = self.get_entry(char_id, "fears")
                        current_fears = existing_fears.current.value if existing_fears and existing_fears.current else []

                        if fear_text not in current_fears:
                            new_fears = current_fears + [fear_text]
                            self.update_entry(
                                char_id,
                                "fears",
                                new_fears,
                                chapter=chapter_num,
                                evidence_ids=[],
                                confidence=0.65,
                                reasoning=f"Fear extracted from text containing '{indicator}'.",
                                importance=0.85,
                            )
                            changes.append(
                                StateChange(
                                    change_type=StateChangeType.EVOLUTION,
                                    target_type=NarrativeElementType.CHARACTER,
                                    target_id=char_id,
                                    field_key="fears",
                                    old_value=current_fears,
                                    new_value=new_fears,
                                    confidence=0.65,
                                    reasoning=f"New fear identified from chapter text.",
                                )
                            )
                        break

        return changes

    def _update_arc_stage(
        self,
        chapter_data: ChapterData,
        char_id: str,
        name_variants: Set[str],
        chapter_num: int,
        coref_map: Dict[str, str],
    ) -> List[StateChange]:
        """Update character arc stage based on chapter events."""
        changes: List[StateChange] = []

        # Get current arc stage
        existing_arc = self.get_entry(char_id, "arc_stage")
        current_stage = existing_arc.current.value if existing_arc and existing_arc.current else "introduction"

        # Simple heuristic: arc progression based on chapter number and mention count
        mention_entry = self.get_entry(char_id, "mention_count")
        mention_count = mention_entry.current.value if mention_entry and mention_entry.current else 0

        # Determine new arc stage based on heuristics
        new_stage = current_stage
        if chapter_num <= 2:
            new_stage = "introduction"
        elif chapter_num <= 5 and mention_count >= 3:
            new_stage = "inciting_incident"
        elif chapter_num <= 10 and mention_count >= 5:
            new_stage = "rising_action"
        elif chapter_num <= 15 and mention_count >= 8:
            new_stage = "crisis"
        elif chapter_num <= 18 and mention_count >= 10:
            new_stage = "climax"
        elif chapter_num > 18:
            new_stage = "resolution"

        if new_stage != current_stage:
            self.update_entry(
                char_id,
                "arc_stage",
                new_stage,
                chapter=chapter_num,
                evidence_ids=[],
                confidence=0.5,
                reasoning=f"Arc stage updated based on chapter progression (ch{chapter_num}, mentions:{mention_count}).",
                importance=0.8,
            )
            changes.append(
                StateChange(
                    change_type=StateChangeType.EVOLUTION,
                    target_type=NarrativeElementType.CHARACTER,
                    target_id=char_id,
                    field_key="arc_stage",
                    old_value=current_stage,
                    new_value=new_stage,
                    confidence=0.5,
                    reasoning=f"Character arc progressed to new stage.",
                )
            )

        return changes

    def _build_coref_map(self, chapter_data: ChapterData) -> Dict[str, str]:
        """Map coreference mentions to canonical phrase strings."""
        mapping: Dict[str, str] = {}
        for cluster in chapter_data.coreference_clusters:
            canonical = next(
                (mention for mention in cluster if mention.strip().lower() not in self.PRONOUNS),
                cluster[0] if cluster else "",
            )
            canonical = canonical.strip()
            for mention in cluster:
                mapping[mention.strip()] = canonical
        return mapping

    def _collect_character_mentions(
        self,
        chapter_data: ChapterData,
        coref_map: Dict[str, str],
    ) -> List[str]:
        """Collect character mention texts from chapter evidence."""
        mentions: List[str] = []
        seen: set = set()

        def add(text: str) -> None:
            if not text or not text.strip():
                return
            text = text.strip()
            normalized = text.lower()
            if normalized in self.PRONOUNS:
                return
            text = coref_map.get(text, text)
            normalized = text.lower()
            if normalized in seen:
                return
            seen.add(normalized)
            mentions.append(text)

        for entity in chapter_data.entities:
            if entity.label.lower() == "person":
                add(entity.text)

        for relation in chapter_data.relations:
            add(relation.subject)
            add(relation.object)

        for dialogue in chapter_data.dialogues:
            if dialogue.speaker and dialogue.speaker.strip().lower() != "unknown":
                add(dialogue.speaker)

        return mentions

    def _normalize_entity_id(self, text: str) -> str:
        """Normalize a mention into a stable character identifier."""
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text

    def resolve_character_id(self, mention_text: str, existing_entries: Dict[str, Dict[str, object]]) -> str:
        # First, check direct normalization
        normalized_id = self._normalize_entity_id(mention_text)
        if normalized_id in existing_entries:
            return normalized_id
        
        # If not found directly, check for alias overlap
        mention_lower = mention_text.strip().lower()
        mention_words = set(w for w in mention_lower.split() if w not in {"mr", "mrs", "sir", "lord", "lady", "detective", "captain", "miss", "dr"})
        
        best_match_id = None
        best_score = 0.0
        
        import logging
        logger = logging.getLogger("NarrativeEngine.Memory.Character")
        
        for char_id, char_fields in existing_entries.items():
            # Check canonical name
            canonical_entry = char_fields.get("canonical_name")
            canonical_name = canonical_entry.current.value.strip().lower() if canonical_entry and canonical_entry.current else ""
            
            # Check aliases
            alias_entry = char_fields.get("aliases")
            aliases = [a.strip().lower() for a in alias_entry.current.value] if alias_entry and alias_entry.current else []
            
            # Direct match with any alias or canonical name
            if mention_lower == canonical_name or mention_lower in aliases:
                return char_id
            
            # Word overlap match
            for name in [canonical_name] + aliases:
                name_words = set(w for w in name.split() if w not in {"mr", "mrs", "sir", "lord", "lady", "detective", "captain", "miss", "dr"})
                if not name_words or not mention_words:
                    continue
                overlap = name_words.intersection(mention_words)
                if overlap:
                    score = len(overlap) / max(len(name_words), len(mention_words))
                    # If substantial overlap (e.g. >= 0.5 or sharing key name), consider a match
                    if score > best_score:
                        best_score = score
                        best_match_id = char_id
                        
        if best_score >= 0.5:
            logger.info(f"Auto-merged mention '{mention_text}' into existing character ID '{best_match_id}' (overlap score: {best_score:.2f})")
            return best_match_id
            
        return normalized_id

    def _extract_inventory(self, chapter_data: ChapterData, char_id: str, name_variants: Set[str], chapter_num: int, coref_map: Dict[str, str]) -> List[StateChange]:
        changes = []
        text = chapter_data.raw_text.lower()
        
        # Find all objects mentioned in sentences containing the character name/alias
        for ent in chapter_data.entities:
            if ent.label.lower() != "object":
                continue
            item_name = ent.text.strip()
            
            for sentence in chapter_data.sentences:
                sentence_lower = sentence.lower()
                if item_name.lower() in sentence_lower and any(v in sentence_lower for v in name_variants):
                    # Determine if obtaining or dropping
                    obtaining_verbs = ["take", "took", "grab", "grabbed", "pick", "picked", "hold", "held", "find", "found", "has", "had", "wield", "wielded", "carry", "carried", "obtain", "obtained", "use", "used", "drew"]
                    dropping_verbs = ["drop", "dropped", "lose", "lost", "leave", "left", "throw", "threw", "abandon", "abandoned", "put down"]
                    
                    is_obtaining = any(v in sentence_lower for v in obtaining_verbs)
                    is_dropping = any(v in sentence_lower for v in dropping_verbs)
                    
                    # Get current inventory
                    existing = self.get_entry(char_id, "inventory")
                    current_inv = list(existing.current.value) if existing and existing.current else []
                    
                    if is_obtaining and item_name not in current_inv:
                        new_inv = current_inv + [item_name]
                        self.update_entry(
                            char_id,
                            "inventory",
                            new_inv,
                            chapter=chapter_num,
                            evidence_ids=[ent.span.text] if ent.span else [],
                            confidence=0.7,
                            reasoning=f"Obtained '{item_name}' (implied by sentence: '{sentence}')",
                        )
                        changes.append(
                            StateChange(
                                change_type=StateChangeType.EVOLUTION,
                                target_type=NarrativeElementType.CHARACTER,
                                target_id=char_id,
                                field_key="inventory",
                                old_value=current_inv,
                                new_value=new_inv,
                                confidence=0.7,
                                reasoning=f"Character obtained item: {item_name}",
                            )
                        )
                        
                    elif is_dropping and item_name in current_inv:
                        new_inv = [i for i in current_inv if i != item_name]
                        self.update_entry(
                            char_id,
                            "inventory",
                            new_inv,
                            chapter=chapter_num,
                            evidence_ids=[ent.span.text] if ent.span else [],
                            confidence=0.7,
                            reasoning=f"Dropped '{item_name}' (implied by sentence: '{sentence}')",
                        )
                        changes.append(
                            StateChange(
                                change_type=StateChangeType.EVOLUTION,
                                target_type=NarrativeElementType.CHARACTER,
                                target_id=char_id,
                                field_key="inventory",
                                old_value=current_inv,
                                new_value=new_inv,
                                confidence=0.7,
                                reasoning=f"Character dropped item: {item_name}",
                            )
                        )
        return changes
