"""
Dialogue Extractor - quoted speech evidence for ChapterData.

This module extracts dialogue from the current chapter only. It does not build
voice models, infer long-term speaker habits, or update narrative state.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from src.models.state import ExtractedDialogue, TextSpan

logger = logging.getLogger("NarrativeEngine.Pipeline.Dialogue")


class DialogueExtractor:
    """Extract quoted dialogue and lightweight speaker attribution evidence."""

    SPEECH_VERBS = (
        "said", "asked", "replied", "whispered", "shouted", "murmured",
        "called", "answered", "cried", "snapped", "continued", "added",
    )

    NAME_PATTERN = r"[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,2}"

    def extract(self, text: str, sentence_spans: Optional[List[TextSpan]] = None) -> List[ExtractedDialogue]:
        """Extract dialogue utterances from normalized chapter text."""
        if not text:
            return []

        dialogues: List[ExtractedDialogue] = []
        for match in re.finditer(r'"([^"\n]+)"', text):
            quote_text = match.group(1).strip()
            speaker, confidence, method = self._attribute_speaker(text, match.start(), match.end())
            span = TextSpan(
                text=match.group(0),
                start_char=match.start(),
                end_char=match.end(),
                sentence_index=self._sentence_index(match.start(), sentence_spans),
            )
            dialogues.append(
                ExtractedDialogue(
                    speaker=speaker,
                    text=quote_text,
                    span=span,
                    confidence=confidence,
                    attribution_method=method,
                )
            )

        logger.info(f"Extracted {len(dialogues)} dialogue utterances")
        return dialogues

    def _attribute_speaker(self, text: str, quote_start: int, quote_end: int) -> Tuple[str, float, str]:
        """Use local speech-tag patterns around a quote to attribute speaker evidence."""
        before = text[max(0, quote_start - 140):quote_start]
        after = text[quote_end:quote_end + 140]
        verbs = "|".join(self.SPEECH_VERBS)

        patterns = [
            (rf"^\s*,?\s*(?:{verbs})\s+({self.NAME_PATTERN})\b", after, "speech_tag_after"),
            (rf"^\s*,?\s*({self.NAME_PATTERN})\s+(?:{verbs})\b", after, "speaker_before_verb_after"),
            (rf"({self.NAME_PATTERN})\s+(?:{verbs})\s*,?\s*$", before, "speech_tag_before"),
        ]

        for pattern, context, method in patterns:
            match = re.search(pattern, context)
            if match:
                return match.group(1).strip(), 0.8, method

        return "Unknown", 0.25, "unattributed_quote"

    def _sentence_index(self, char_index: int, sentence_spans: Optional[List[TextSpan]]) -> Optional[int]:
        if not sentence_spans:
            return None
        for span in sentence_spans:
            if span.start_char <= char_index < span.end_char:
                return span.sentence_index
        return None
