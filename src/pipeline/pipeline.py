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

from src.models.state import ChapterData, TextSpan
from src.pipeline.parser import DocumentParser
from src.pipeline.cleaner import TextCleaner
from src.pipeline.segmenter import SentenceSegmenter
from src.pipeline.nlp import NLPProcessor
from src.pipeline.ner import EntityExtractor
from src.pipeline.coref import CoreferenceResolver
from src.pipeline.dialogue import DialogueExtractor

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

    def __init__(
        self,
        config=None,
        entity_extractor=None,
        coreference_resolver=None,
    ):
        self._config = config
        self._parser = DocumentParser()
        self._cleaner = TextCleaner()
        self._nlp_processor = NLPProcessor(
            model_name=config.get("pipeline.spacy_model", "en_core_web_sm")
            if config else "en_core_web_sm"
        )
        self._segmenter = None  # Initialized after NLP loads
        self._dialogue_extractor = DialogueExtractor()

        # Phase 4 components (lazy-loaded, injectable for tests)
        self._ner = entity_extractor
        self._coref = coreference_resolver

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
            source_name = Path(source).name
            logger.info(f"Parsed file: {Path(source).name} ({len(raw_text)} chars)")
        else:
            raw_text = source
            source_name = ""
            logger.info(f"Received raw text ({len(raw_text)} chars)")

        # Step 2: Clean text
        cleaned_text = self._cleaner.clean(raw_text)
        logger.info(f"Cleaned text: {len(cleaned_text)} chars")

        # Step 2b: Caching lookup
        use_cache = self._config.get("pipeline.use_cache", True) if self._config else True
        cache_file = None
        if use_cache and self._config:
            import hashlib
            import json
            text_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
            cache_file = Path(self._config.cache_dir) / f"chapter_{chapter_num}_{text_hash[:16]}.json"
            if cache_file.exists():
                logger.info(f"Cache hit: Loading Chapter {chapter_num} data from {cache_file.name}")
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                    return ChapterData.from_dict(cached_data)
                except Exception as e:
                    logger.warning(f"Failed to load cached chapter data: {e}. Re-processing...")

        # Step 3: Segment into sentences
        segmenter = self._get_segmenter()
        paragraphs = segmenter.split_into_paragraphs(cleaned_text)
        sentences = segmenter.split(cleaned_text)
        sentence_spans = self._sentence_spans(cleaned_text, sentences)
        logger.info(f"Segmented into {len(sentences)} sentences")

        # Build initial ChapterData with what we have
        chapter_data = ChapterData(
            chapter_number=chapter_num,
            source_name=source_name,
            chapter_title=self._extract_chapter_title(paragraphs),
            raw_text=cleaned_text,
            paragraphs=paragraphs,
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
                    span=self._span_for_sentence(cleaned_text, t.get("sentence"), sentence_spans),
                    source="spacy_svo",
                )
                for t in svo_triples
            ]
            logger.info(f"Extracted {len(svo_triples)} SVO triples")

            # Compute basic style metrics
            chapter_data.style_metrics = self._compute_style_metrics(doc, sentences)

        except (ImportError, OSError) as e:
            logger.warning(f"spaCy processing skipped: {e}")

        # Step 5: NER (Phase 4)
        try:
            chapter_data.entities = self._get_entity_extractor().extract(
                cleaned_text,
                labels=self._entity_labels(),
            )
            self._normalize_entities(chapter_data)
            logger.info(f"Extracted {len(chapter_data.entities)} entities")
        except (ImportError, OSError) as e:
            logger.warning(f"GLiNER entity extraction skipped: {e}")

        # Step 6: Coreference resolution (Phase 4)
        try:
            chapter_data.coreferences = self._get_coreference_resolver().resolve(cleaned_text)
            self._normalize_coreferences(chapter_data)
            chapter_data.coreference_clusters = [
                cluster.mentions for cluster in chapter_data.coreferences
            ]
            self._attach_coreference_ids(chapter_data)
            logger.info(f"Resolved {len(chapter_data.coreferences)} coreference clusters")
        except (ImportError, OSError) as e:
            logger.warning(f"FastCoref resolution skipped: {e}")

        # Step 7: Dialogue evidence (Phase 5)
        chapter_data.dialogues = self._dialogue_extractor.extract(cleaned_text, sentence_spans)

        # Step 8: Final evidence package validation (Phase 5)
        chapter_data.validate()

        # Save to cache if enabled
        if use_cache and cache_file:
            try:
                import json
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(chapter_data.to_dict(), f, indent=2, ensure_ascii=False)
                logger.info(f"Cached Chapter {chapter_num} data to {cache_file.name}")
            except Exception as e:
                logger.warning(f"Failed to cache chapter data: {e}")

        logger.info(f"=== Chapter {chapter_num} evidence extraction complete ===")
        return chapter_data

    def _get_entity_extractor(self):
        """Get the GLiNER-backed entity extractor."""
        if self._ner is None:
            model_name = (
                self._config.get("pipeline.gliner_model", "gliner-community/gliner_small-v2.5")
                if self._config else "gliner-community/gliner_small-v2.5"
            )
            threshold = (
                self._config.get("pipeline.gliner_threshold", 0.5)
                if self._config else 0.5
            )
            self._ner = EntityExtractor(model_name=model_name, threshold=threshold)
        return self._ner

    def _get_coreference_resolver(self):
        """Get the FastCoref-backed coreference resolver."""
        if self._coref is None:
            self._coref = CoreferenceResolver(device="cpu")
        return self._coref

    def _entity_labels(self) -> list:
        """Get configured narrative entity labels."""
        default_labels = ["person", "location", "organization", "object", "event", "time"]
        if not self._config:
            return default_labels
        return self._config.get("pipeline.entity_labels", default_labels)

    def _attach_coreference_ids(self, chapter_data: ChapterData) -> None:
        """Annotate extracted entities with matching coreference cluster IDs."""
        mention_to_cluster = {}
        for index, cluster in enumerate(chapter_data.coreferences):
            for mention in cluster.mentions:
                mention_to_cluster[mention.strip().lower()] = index

        for entity in chapter_data.entities:
            entity.coreference_cluster = mention_to_cluster.get(entity.text.strip().lower())

    def _sentence_spans(self, text: str, sentences: list) -> list:
        """Build approximate character spans for sentence strings."""
        spans = []
        cursor = 0
        for index, sentence in enumerate(sentences):
            start = text.find(sentence, cursor)
            if start == -1:
                start = text.find(sentence)
            if start == -1:
                continue
            end = start + len(sentence)
            spans.append(
                TextSpan(
                    text=sentence,
                    start_char=start,
                    end_char=end,
                    sentence_index=index,
                )
            )
            cursor = end
        return spans

    def _span_for_sentence(self, text: str, sentence: Optional[str], sentence_spans: list):
        """Find a TextSpan for a sentence-level extraction."""
        if not sentence:
            return None
        for span in sentence_spans:
            if span.text == sentence:
                return span
        start = text.find(sentence)
        if start == -1:
            return None
        return TextSpan(text=sentence, start_char=start, end_char=start + len(sentence))

    def _extract_chapter_title(self, paragraphs: list) -> str:
        """Use an obvious first-line heading as chapter title evidence."""
        if not paragraphs:
            return ""
        first = paragraphs[0].strip()
        if len(first) <= 120 and first.lower().startswith(("chapter", "prologue", "epilogue")):
            return first
        return ""

    def _normalize_entities(self, chapter_data: ChapterData) -> None:
        """Normalize entity evidence without converting it into state."""
        for entity in chapter_data.entities:
            entity.normalized_text = self._normalize_text_key(entity.text)
            if entity.source == "unknown":
                entity.source = "gliner"

    def _normalize_coreferences(self, chapter_data: ChapterData) -> None:
        """Add IDs and canonical mentions to coreference evidence."""
        for index, cluster in enumerate(chapter_data.coreferences):
            cluster.cluster_id = index
            if not cluster.canonical_mention and cluster.mentions:
                cluster.canonical_mention = cluster.mentions[0]
            if cluster.source == "unknown":
                cluster.source = "fastcoref"

    def _normalize_text_key(self, text: str) -> str:
        """Normalize surface text for evidence matching only."""
        return " ".join(text.strip().lower().split())

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
