"""
Zero-Shot Classifier — optional NLI-based sentence labeling.

Wraps a `transformers` zero-shot-classification pipeline
(`facebook/bart-large-mnli`) so `ThemeMemory`/`MysteryMemory` can classify
sentences against arbitrary candidate labels instead of relying purely on
fixed keyword lists.

This is deliberately an *optional* capability: `transformers`/`torch` are
a ~1.6GB dependency the rest of this project avoids (see requirements.txt
— VADER/textstat were chosen specifically to avoid a model download). If
the dependency isn't installed, or the model can't be loaded for any
reason (no internet, OOM, corrupted cache, ...), this module marks itself
permanently unavailable for the process lifetime and callers fall back to
their existing keyword-based logic. No exception from this module should
ever propagate to a caller.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("NarrativeEngine.Utils.ZeroShotClassifier")

_MODEL_NAME = "facebook/bart-large-mnli"


class ZeroShotClassifier:
    """Lazily-loaded, process-wide singleton around a zero-shot-classification
    pipeline. Construct via `get_classifier()`, not directly."""

    def __init__(self) -> None:
        self._pipeline = None
        self._load_attempted = False
        self._available = False

    def _ensure_loaded(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        try:
            from transformers import pipeline  # type: ignore

            self._pipeline = pipeline("zero-shot-classification", model=_MODEL_NAME)
            self._available = True
            logger.info(f"Zero-shot classifier loaded ({_MODEL_NAME}).")
        except Exception as e:  # noqa: BLE001 - any failure here means "unavailable"
            self._pipeline = None
            self._available = False
            logger.warning(
                f"Zero-shot classifier unavailable ({e.__class__.__name__}: {e}). "
                "Falling back to keyword-based detection for this process."
            )

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    def classify_batch(
        self, texts: List[str], labels: List[str], multi_label: bool = True
    ) -> Optional[List[Dict[str, float]]]:
        """Classify each text against every label.

        Returns a list (one entry per input text) of `{label: score}` dicts,
        or `None` if the classifier is unavailable or the call fails for any
        reason. Never raises.
        """
        if not texts or not labels:
            return [] if texts is not None else None

        if not self.available:
            return None

        try:
            results = self._pipeline(texts, candidate_labels=labels, multi_label=multi_label)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Zero-shot classification call failed ({e.__class__.__name__}: {e}).")
            return None

        # transformers returns a single dict (not a list) when given one text.
        if isinstance(results, dict):
            results = [results]

        return [dict(zip(r["labels"], r["scores"])) for r in results]


_classifier: Optional[ZeroShotClassifier] = None


def get_classifier() -> ZeroShotClassifier:
    """Process-wide singleton accessor."""
    global _classifier
    if _classifier is None:
        _classifier = ZeroShotClassifier()
    return _classifier


def reset_classifier() -> None:
    """Test-only hook: drop the singleton so the next `get_classifier()` call
    re-attempts loading (or can be swapped for a mock)."""
    global _classifier
    _classifier = None
