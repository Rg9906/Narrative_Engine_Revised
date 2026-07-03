"""
Pipeline Orchestrator — Chains all evidence extraction stages.

This is the top-level pipeline that takes raw input (file or text) and
produces a ChapterData object containing all extracted evidence.

The pipeline is the SENSORY SYSTEM — it sees and hears.
The Narrative State Engine is the BRAIN — it understands.

Flow:
  File/Text → Parse → Clean → Segment → NLP → NER → Coref → ChapterData
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.models.state import ChapterData
from src.pipeline.parser import DocumentParser
from src.pipeline.cleaner import TextCleaner
from src.pipeline.segmenter import SentenceSegmenter
from src.pipeline.nlp import NLPProcessor

logger = logging.getLogger("NarrativeEngine.Pipeline")


class Pipeline:
    """
    Orchestrates the full NLP evidence extraction pipeline.

    Takes a chapter (file or raw text) and produces a ChapterData object
    containing all extracted evidence: entities, coreferences, relations,
    dialogue attributions, and style metrics.

    This is EVIDENCE — not understanding. The ChapterData output feeds
    into the Narrative State Engine, which interprets it into state changes.

    Usage:
        pipeline = Pipeline()
        chapter_data = pipeline.process_chapter("chapter_01.txt", chapter_num=1)
    """

    def __init__(self, config=None):
        self._config = config
        self._parser = DocumentParser()
        self._cleaner = TextCleaner()
        self._nlp_processor = NLPProcessor(
            model_name=config.get("pipeline.spacy_model", "en_core_web_sm")
            if config else "en_core_web_sm"
        )
        self._segmenter = None  # Initialized after NLP loads

        # Phase 4 components (lazy-loaded)
        self._ner = None
        self._coref = None

    def _get_segmenter(self) -> SentenceSegmenter:
        """Get segmenter, initializing with spaCy if available."""
        if self._segmenter is None:
            try:
                nlp = self._nlp_processor.nlp
                self._segmenter = SentenceSegmenter(nlp=nlp)
            except (ImportError, OSError):
                logger.warning("spaCy not available, using regex segmenter")
                self._segmenter = SentenceSegmenter(nlp=None)
        return self._segmenter

    def process_chapter(
        self,
        source: str,
        chapter_num: int = 1,
        is_file: bool = True,
    ) -> ChapterData:
        """
        Process a chapter through the full evidence extraction pipeline.

        Args:
            source: File path (if is_file=True) or raw text string.
            chapter_num: Chapter number for tracking.
            is_file: Whether source is a file path or raw text.

        Returns:
            ChapterData containing all extracted evidence.
        """
        logger.info(f"=== Processing Chapter {chapter_num} ===")

        # Step 1: Get raw text
        if is_file:
            raw_text = self._parser.parse(source)
            logger.info(f"Parsed file: {Path(source).name} ({len(raw_text)} chars)")
        else:
            raw_text = source
            logger.info(f"Received raw text ({len(raw_text)} chars)")

        # Step 2: Clean text
        cleaned_text = self._cleaner.clean(raw_text)
        logger.info(f"Cleaned text: {len(cleaned_text)} chars")

        # Step 3: Segment into sentences
        segmenter = self._get_segmenter()
        sentences = segmenter.split(cleaned_text)
        logger.info(f"Segmented into {len(sentences)} sentences")

        # Build initial ChapterData with what we have
        chapter_data = ChapterData(
            chapter_number=chapter_num,
            raw_text=cleaned_text,
            sentences=sentences,
        )

        # Step 4: NLP processing (spaCy)
        try:
            doc = self._nlp_processor.process(cleaned_text)

            # Extract basic SVO triples as relation evidence
            svo_triples = self._nlp_processor.extract_subject_verb_object(doc)
            from src.models.state import ExtractedRelation
            chapter_data.relations = [
                ExtractedRelation(
                    subject=t["subject"],
                    predicate=t["verb"],
                    object=t["object"],
                )
                for t in svo_triples
            ]
            logger.info(f"Extracted {len(svo_triples)} SVO triples")

            # Compute basic style metrics
            chapter_data.style_metrics = self._compute_style_metrics(doc, sentences)

        except (ImportError, OSError) as e:
            logger.warning(f"spaCy processing skipped: {e}")

        # Step 5: NER (Phase 4 — lazy loaded)
        # Step 6: Coref (Phase 4 — lazy loaded)

        logger.info(f"=== Chapter {chapter_num} evidence extraction complete ===")
        return chapter_data

    def _compute_style_metrics(self, doc, sentences: list) -> dict:
        """
        Compute basic style metrics as evidence about the author's writing.

        These feed into the style state of the Narrative State Engine.
        """
        word_count = len([t for t in doc if not t.is_punct and not t.is_space])
        avg_sentence_length = word_count / max(len(sentences), 1)

        # POS distribution
        pos_counts = {}
        for token in doc:
            pos = token.pos_
            pos_counts[pos] = pos_counts.get(pos, 0) + 1

        # Dialogue density (rough: count quoted text)
        quote_count = sum(1 for t in doc if t.text in ('"', "'", "\u201c", "\u201d"))
        dialogue_density = quote_count / max(word_count, 1)

        return {
            "word_count": word_count,
            "sentence_count": len(sentences),
            "avg_sentence_length": round(avg_sentence_length, 2),
            "pos_distribution": pos_counts,
            "dialogue_density": round(dialogue_density, 4),
        }
