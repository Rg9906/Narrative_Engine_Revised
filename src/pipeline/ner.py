"""
Entity Extractor — GLiNER integration for Named Entity Recognition.

Extracts entities from text as EVIDENCE for the Narrative State Engine.
The entities extracted here are raw observations — they become characters,
locations, and objects only after the state engine interprets them.

Implementation: Phase 4
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.models.state import ExtractedEntity, TextSpan

logger = logging.getLogger("NarrativeEngine.Pipeline.NER")


class EntityExtractor:
    """
    Wraps GLiNER for flexible named entity recognition.

    GLiNER can extract any entity type in a single pass, making it ideal
    for narrative processing where we need characters, locations, objects,
    events, and more.

    Usage:
        extractor = EntityExtractor()
        entities = extractor.extract("Alice walked to the Silver Gate.",
                                     labels=["person", "location"])
    """

    def __init__(self, model_name: str = "gliner-community/gliner_small-v2.5",
                 threshold: float = 0.5):
        self._model_name = model_name
        self._threshold = threshold
        self._model = None

    def _ensure_loaded(self):
        """Lazy-load the GLiNER model."""
        if self._model is None:
            try:
                from gliner import GLiNER
                logger.info(f"Loading GLiNER model: {self._model_name}")
                self._model = GLiNER.from_pretrained(self._model_name)
                logger.info("GLiNER model loaded successfully")
            except ImportError:
                raise ImportError(
                    "GLiNER is required for entity extraction. "
                    "Install with: pip install gliner"
                )

    def extract(self, text: str, labels: Optional[List[str]] = None, doc = None) -> List[ExtractedEntity]:
        """
        Extract entities from text.

        Args:
            text: Input text to extract entities from.
            labels: Entity types to extract. Defaults to narrative-relevant types.
            doc: Optional pre-parsed spaCy doc for linguistic filtering.

        Returns:
            List of ExtractedEntity objects (evidence, not state).
        """
        self._ensure_loaded()

        if labels is None:
            labels = ["person", "location", "organization", "object", "event", "time"]

        raw_entities = self._model.predict_entities(text, labels, threshold=self._threshold)

        # Ensure we have a spaCy doc for POS tagging if not provided
        if doc is None:
            try:
                import spacy
                nlp = spacy.load("en_core_web_sm")
                doc = nlp(text)
            except Exception:
                pass

        dirty_words = {"that", "eyes", "men", "oath", "hand", "cloak", "this", "it", "she", "he", "they", "we", "them", "him", "her", "i", "me", "you"}

        entities = []
        for ent in raw_entities:
            ent_text = ent["text"]
            ent_label = ent["label"]

            # Filter out dirty words
            if ent_text.lower() in dirty_words:
                continue

            # Check if person consists purely of lower-case common nouns, pronouns, or conjunctions
            if doc is not None and ent_label.lower() == "person":
                char_span = doc.char_span(ent["start"], ent["end"])
                if char_span is not None:
                    all_dirty_pos = True
                    has_propn = False
                    for t in char_span:
                        if t.is_punct or t.is_space:
                            continue
                        if t.pos_ == "PROPN":
                            has_propn = True
                        is_token_dirty = (t.pos_ in ("NOUN", "PRON", "CCONJ") and t.text == t.text.lower())
                        if not is_token_dirty:
                            all_dirty_pos = False
                    # Discard if it consists purely of lower-case nouns/pronouns/conjunctions
                    if all_dirty_pos or (not has_propn and all(t.pos_ in ("NOUN", "PRON", "CCONJ", "DET", "ADP") or t.text.lower() in dirty_words for t in char_span)):
                        continue

            span = None
            if "start" in ent and "end" in ent:
                span = TextSpan(
                    text=ent["text"],
                    start_char=ent["start"],
                    end_char=ent["end"],
                )
            entities.append(ExtractedEntity(
                text=ent["text"],
                label=ent["label"],
                span=span,
                confidence=ent.get("score", 1.0),
            ))

        logger.info(f"Extracted {len(entities)} entities from text")
        return entities
