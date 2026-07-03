"""
Coreference Resolver — FastCoref integration.

Resolves pronoun and noun phrase coreferences to link mentions of the
same entity across a chapter. This is critical evidence for the Narrative
State Engine — without coreference, "she" could be anyone.

Implementation: Phase 4
"""

from __future__ import annotations

import logging
from typing import List

from src.models.state import ExtractedCoreferenceCluster

logger = logging.getLogger("NarrativeEngine.Pipeline.Coref")


class CoreferenceResolver:
    """
    Wraps FastCoref for coreference resolution.

    Produces coreference clusters — groups of text spans that refer to the
    same entity. This is evidence that helps the state engine understand
    which mentions refer to which characters.

    Usage:
        resolver = CoreferenceResolver()
        clusters = resolver.resolve("Alice walked home. She was tired.")
        # → [["Alice", "She"]]
    """

    def __init__(self, device: str = "cpu"):
        self._device = device
        self._model = None

    def _ensure_loaded(self):
        """Lazy-load the FastCoref model."""
        if self._model is None:
            try:
                from fastcoref import FCoref
                logger.info("Loading FastCoref model...")
                self._model = FCoref(device=self._device)
                logger.info("FastCoref model loaded successfully")
            except ImportError:
                raise ImportError(
                    "FastCoref is required for coreference resolution. "
                    "Install with: pip install fastcoref"
                )

    def resolve(self, text: str) -> List[ExtractedCoreferenceCluster]:
        """
        Resolve coreferences in text.

        Args:
            text: Input text to resolve coreferences in.

        Returns:
            List of coreference clusters. Each cluster contains mentions
            that refer to the same entity.
        """
        self._ensure_loaded()

        preds = self._model.predict(texts=[text])
        raw_clusters = preds[0].get_clusters()
        clusters = [
            ExtractedCoreferenceCluster(
                mentions=list(cluster),
                canonical_mention=self._canonical_mention(cluster),
            )
            for cluster in raw_clusters
        ]

        logger.info(f"Resolved {len(clusters)} coreference clusters")
        return clusters

    def _canonical_mention(self, cluster) -> str:
        """Pick a stable representative mention for a coreference cluster."""
        pronouns = {
            "i", "me", "you", "he", "him", "she", "her", "they", "them",
            "we", "us", "it", "its", "his", "hers", "their", "theirs",
        }
        for mention in cluster:
            if mention.strip().lower() not in pronouns:
                return mention.strip()
        return cluster[0].strip() if cluster else ""
