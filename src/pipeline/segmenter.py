"""
Sentence Segmenter — Splits cleaned text into sentences.

Part of the evidence extraction pipeline. Sentences are the atomic unit
for most NLP analysis (NER, coreference, dependency parsing).

Uses spaCy's sentence tokenizer for accurate boundary detection,
with a fallback to regex-based splitting if spaCy is unavailable.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

logger = logging.getLogger("NarrativeEngine.Pipeline.Segmenter")


class SentenceSegmenter:
    """
    Splits text into individual sentences.

    Primary method uses spaCy's sentence tokenizer for accuracy.
    Falls back to regex-based splitting if spaCy is not available.

    Usage:
        segmenter = SentenceSegmenter()
        sentences = segmenter.split("Hello world. How are you?")
        # → ["Hello world.", "How are you?"]
    """

    def __init__(self, nlp=None):
        """
        Args:
            nlp: Optional spaCy Language model. If provided, uses it for
                 sentence tokenization. If None, uses regex fallback.
        """
        self._nlp = nlp

    def split(self, text: str) -> List[str]:
        """
        Split text into sentences.

        Args:
            text: Cleaned text to segment.

        Returns:
            List of sentence strings.
        """
        if not text or not text.strip():
            return []

        if self._nlp is not None:
            return self._split_spacy(text)
        else:
            return self._split_regex(text)

    def _split_spacy(self, text: str) -> List[str]:
        """Use spaCy's sentence tokenizer for accurate splitting."""
        doc = self._nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        logger.debug(f"spaCy segmenter: {len(sentences)} sentences")
        return sentences

    def _split_regex(self, text: str) -> List[str]:
        """
        Regex-based sentence splitting as a fallback.

        Handles common abbreviations and avoids splitting on Mr./Mrs./Dr. etc.
        """
        # Protect common abbreviations
        abbreviations = [
            "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.",
            "St.", "Ave.", "Blvd.", "etc.", "vs.", "i.e.", "e.g.",
        ]
        protected = text
        for abbr in abbreviations:
            protected = protected.replace(abbr, abbr.replace(".", "<DOT>"))

        # Split on sentence-ending punctuation followed by whitespace and capital
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', protected)

        # Restore abbreviations
        sentences = []
        for part in parts:
            part = part.replace("<DOT>", ".")
            part = part.strip()
            if part:
                sentences.append(part)

        logger.debug(f"Regex segmenter: {len(sentences)} sentences")
        return sentences

    def split_into_paragraphs(self, text: str) -> List[str]:
        """
        Split text into paragraphs (separated by double newlines).

        Useful for scene boundary detection upstream.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        logger.debug(f"Paragraph segmenter: {len(paragraphs)} paragraphs")
        return paragraphs
