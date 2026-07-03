"""
Text Cleaner — Normalizes raw text extracted by the parser.

Part of the evidence extraction pipeline. Cleans text so downstream
NLP components receive consistent input.

This does NOT interpret content — it merely prepares it for processing.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("NarrativeEngine.Pipeline.Cleaner")


class TextCleaner:
    """
    Cleans and normalizes raw text for downstream NLP processing.

    Operations:
      - Remove HTML/XML tags
      - Normalize whitespace (collapse multiple spaces/newlines)
      - Fix encoding artifacts (smart quotes, em dashes, etc.)
      - Normalize quotation marks for consistent dialogue detection
      - Preserve paragraph boundaries (double newlines)
    """

    def clean(self, text: str) -> str:
        """
        Clean raw text and return normalized version.

        Args:
            text: Raw text from the document parser.

        Returns:
            Cleaned, normalized text string.
        """
        if not text or not text.strip():
            return ""

        logger.debug(f"Cleaning text ({len(text)} chars)")

        text = self._remove_html_tags(text)
        text = self._fix_encoding_artifacts(text)
        text = self._normalize_quotes(text)
        text = self._normalize_whitespace(text)
        text = text.strip()

        logger.debug(f"Cleaned text ({len(text)} chars)")
        return text

    def _remove_html_tags(self, text: str) -> str:
        """Remove HTML/XML tags while preserving content."""
        return re.sub(r"<[^>]+>", "", text)

    def _fix_encoding_artifacts(self, text: str) -> str:
        """Replace common encoding artifacts with standard characters."""
        replacements = {
            "\u2018": "'",   # Left single quote
            "\u2019": "'",   # Right single quote
            "\u201c": '"',   # Left double quote
            "\u201d": '"',   # Right double quote
            "\u2013": "–",   # En dash (keep as-is, it's valid)
            "\u2014": "—",   # Em dash (keep as-is, it's valid)
            "\u2026": "...", # Ellipsis
            "\u00a0": " ",   # Non-breaking space
            "\r\n": "\n",    # Windows line endings
            "\r": "\n",      # Old Mac line endings
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _normalize_quotes(self, text: str) -> str:
        """Normalize curly/smart quotes to straight quotes for consistency."""
        # Already handled in _fix_encoding_artifacts, but this catches
        # any remaining non-standard quote characters
        text = re.sub(r"[\u00ab\u00bb\u2039\u203a]", '"', text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace while preserving paragraph boundaries.

        Single newlines within a paragraph → space
        Multiple newlines (paragraph breaks) → double newline
        Multiple spaces → single space
        """
        # Preserve paragraph breaks (2+ newlines) by marking them
        text = re.sub(r"\n{2,}", "\n\n", text)

        # Within paragraphs, collapse single newlines to spaces
        paragraphs = text.split("\n\n")
        cleaned_paragraphs = []
        for para in paragraphs:
            # Collapse whitespace within paragraph
            para = re.sub(r"[ \t]+", " ", para)
            para = para.replace("\n", " ")
            para = para.strip()
            if para:
                cleaned_paragraphs.append(para)

        return "\n\n".join(cleaned_paragraphs)
