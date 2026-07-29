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
                # Monkey-patch to fix compatibility between newer transformers and fastcoref
                import transformers
                if not hasattr(transformers.PreTrainedModel, "all_tied_weights_keys"):
                    def get_all_tied_weights_keys(self):
                        if not hasattr(self, "_all_tied_weights_keys"):
                            try:
                                self._all_tied_weights_keys = self.get_expanded_tied_weights_keys(all_submodels=False)
                            except Exception:
                                self._all_tied_weights_keys = {}
                        return self._all_tied_weights_keys
                    def set_all_tied_weights_keys(self, value):
                        self._all_tied_weights_keys = value
                    transformers.PreTrainedModel.all_tied_weights_keys = property(
                        get_all_tied_weights_keys, set_all_tied_weights_keys
                    )

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
            that refer to the same entity, along with the character-offset
            span of each mention (see ExtractedCoreferenceCluster.mention_spans).
        """
        self._ensure_loaded()

        preds = self._model.predict(texts=[text])
        # get_clusters(as_strings=False) gives FastCoref's own precise (start, end)
        # character span per mention. Deriving mention text from these spans ourselves
        # (rather than also calling get_clusters(as_strings=True)) keeps mentions and
        # mention_spans guaranteed aligned — the two call paths in fastcoref's own
        # source apply a None-filter asymmetrically and can otherwise silently diverge
        # in length for the same cluster.
        raw_span_clusters = preds[0].get_clusters(as_strings=False)

        clusters = []
        for span_cluster in raw_span_clusters:
            valid_spans = [
                (start, end) for start, end in span_cluster
                if start is not None and end is not None
            ]
            if not valid_spans:
                continue
            mention_texts = [text[start:end] for start, end in valid_spans]
            clusters.append(
                ExtractedCoreferenceCluster(
                    mentions=mention_texts,
                    mention_spans=valid_spans,
                    canonical_mention=self._canonical_mention(mention_texts),
                )
            )

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
