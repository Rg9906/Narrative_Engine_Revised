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

    # Confidence for a turn-taking inference — lower than an explicit local speech tag
    # (0.8) since it's a structural guess, but higher than the "we have no idea" default
    # (0.25), since alternating between exactly two already-established speakers in a
    # back-and-forth exchange is a real, well-founded signal, not a random guess.
    TURN_TAKING_CONFIDENCE = 0.45

    def extract(self, text: str, sentence_spans: Optional[List[TextSpan]] = None) -> List[ExtractedDialogue]:
        """Extract dialogue utterances from normalized chapter text."""
        if not text:
            return []

        # Pass 1: attribute every quote using local speech-tag patterns, exactly as
        # before. Most quotes in a real conversation don't repeat "X said" every line,
        # so this alone leaves the majority "Unknown" (measured 87% unattributed on a
        # real chapter-length two-person phone conversation).
        raw: List[Tuple[re.Match, str, float, str]] = []
        for match in re.finditer(r'"([^"\n]+)"', text):
            speaker, confidence, method = self._attribute_speaker(text, match.start(), match.end())
            raw.append((match, speaker, confidence, method))

        # Pass 2: turn-taking inference. Once exactly two distinct speakers have been
        # confidently established anywhere in the text (via Pass 1's explicit tags),
        # alternate between them for quotes still marked "Unknown" — the standard
        # heuristic for attributing back-and-forth dialogue. Deliberately does NOT guess
        # when 0, 1, or 3+ speakers are known: with 0/1 there's nothing to alternate
        # between, and with 3+ which two are actually in THIS exchange is ambiguous
        # enough that a wrong guess is worse than "Unknown".
        known_speakers: List[str] = []
        for _, speaker, _, _ in raw:
            if speaker != "Unknown" and speaker not in known_speakers:
                known_speakers.append(speaker)

        attributed: List[Tuple[re.Match, str, float, str]] = []
        last_speaker: Optional[str] = None
        for match, speaker, confidence, method in raw:
            if speaker != "Unknown":
                last_speaker = speaker
                attributed.append((match, speaker, confidence, method))
                continue

            if len(known_speakers) == 2 and last_speaker in known_speakers:
                inferred = known_speakers[0] if last_speaker == known_speakers[1] else known_speakers[1]
                attributed.append((match, inferred, self.TURN_TAKING_CONFIDENCE, "turn_taking_inferred"))
                last_speaker = inferred
            else:
                attributed.append((match, speaker, confidence, method))

        dialogues: List[ExtractedDialogue] = []
        for match, speaker, confidence, method in attributed:
            quote_text = match.group(1).strip()
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
