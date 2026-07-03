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

from src.models.state import ExtractedEntity

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

    def extract(self, text: str, labels: Optional[List[str]] = None) -> List[ExtractedEntity]:
        """
        Extract entities from text.

        Args:
            text: Input text to extract entities from.
            labels: Entity types to extract. Defaults to narrative-relevant types.

        Returns:
            List of ExtractedEntity objects (evidence, not state).
        """
        self._ensure_loaded()

        if labels is None:
            labels = ["person", "location", "organization", "object", "event", "time"]

        raw_entities = self._model.predict_entities(text, labels, threshold=self._threshold)

        entities = []
        for ent in raw_entities:
            entities.append(ExtractedEntity(
                text=ent["text"],
                label=ent["label"],
                confidence=ent.get("score", 1.0),
            ))

        logger.info(f"Extracted {len(entities)} entities from text")
        return entities
