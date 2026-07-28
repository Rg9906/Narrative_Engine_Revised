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

import json
import logging
from pathlib import Path
from typing import Optional

from src.models.state import ChapterData, TextSpan, NarrativeState
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
        self._sentiment_analyzer = None  # Lazy-loaded VADER analyzer

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
        current_state: Optional[NarrativeState] = None,
    ) -> ChapterData:
        """
        Process a chapter through the full evidence extraction pipeline.

        Args:
            source: File path (if is_file=True) or raw text string.
            chapter_num: Chapter number for tracking.
            is_file: Whether source is a file path or raw text.
            current_state: Current NarrativeState.

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

        # Step 3: Segment into sentences (Keep spaCy solely for basic paragraph/sentence segmentation)
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
        
        # Initialize default llm_delta attribute
        chapter_data.llm_delta = {}

        # 4. DETERMINISTIC NLP EXTRACTION — PRIMARY evidence source, runs BEFORE any LLM call so
        # every LLM stage below can ground itself in what's already known instead of rediscovering it.
        #
        # GLiNER NER + FastCoref coreference: always run in real usage via the lazy loaders below.
        # Explicit injection (tests) is always honored. Under pytest without injection, real model
        # loading is skipped so unit tests stay fast and offline — mirroring the same
        # PYTEST_CURRENT_TEST convention already used by LLMProvider._detect_backend().
        import os
        in_pytest = "PYTEST_CURRENT_TEST" in os.environ
        ner_ran_ok = False
        coref_ran_ok = False

        if self._ner is not None or not in_pytest:
            try:
                extractor = self._get_entity_extractor()
                import inspect
                sig = inspect.signature(extractor.extract)
                if "doc" in sig.parameters:
                    chapter_data.entities = extractor.extract(
                        cleaned_text,
                        labels=self._entity_labels(),
                        doc=None
                    )
                else:
                    chapter_data.entities = extractor.extract(
                        cleaned_text,
                        labels=self._entity_labels(),
                    )
                self._normalize_entities(chapter_data)
                ner_ran_ok = True
            except Exception as e:
                logger.warning(f"Deterministic NER extraction failed, will fall back to regex entities: {e}")

        if self._coref is not None or not in_pytest:
            try:
                chapter_data.coreferences = self._get_coreference_resolver().resolve(cleaned_text)
                self._normalize_coreferences(chapter_data)
                chapter_data.coreference_clusters = [
                    cluster.mentions for cluster in chapter_data.coreferences
                ]
                self._attach_coreference_ids(chapter_data)
                coref_ran_ok = True
            except Exception as e:
                logger.warning(f"Deterministic coreference resolution failed: {e}")

        # Fast Rule-based Fallback Parser — only used if deterministic NER didn't run/succeed
        # (test mode without injection, or a genuine GLiNER load/runtime failure).
        from src.models.state import ExtractedEntity, ExtractedDialogue, TextSpan

        if not ner_ran_ok:
            existing_texts = {e.text.lower() for e in chapter_data.entities}
            import re
            matches = re.finditer(r'\b[A-Z][a-zA-Z]+\b', cleaned_text)
            for m in matches:
                name = m.group()
                if name.lower() not in ("the", "a", "an", "chapter", "he", "she", "it", "they", "we", "you", "in", "on", "at", "to", "for", "with", "by", "of", "and", "or", "but"):
                    if name.lower() not in existing_texts:
                        idx = m.start()
                        label = "person"
                        if name.lower() in ("castle", "drawing_room", "family_library", "morning_room", "kitchen", "garden", "bridge"):
                            label = "location"
                        chapter_data.entities.append(ExtractedEntity(
                            text=name, label=label,
                            span=TextSpan(text=name, start_char=idx, end_char=idx+len(name)),
                            confidence=0.8, source="regex_fallback"
                        ))
                        existing_texts.add(name.lower())

        # Unconditionally run Dialogue Extraction (fast, rule-based)
        chapter_data.dialogues = self._dialogue_extractor.extract(cleaned_text, sentence_spans)

        # Dependency-parsed relation extraction (subject/verb/object) + style metrics. Both were
        # previously dormant: NLPProcessor.extract_subject_verb_object() and
        # Pipeline._compute_style_metrics() existed but nothing called them, leaving
        # chapter_data.relations always empty (silently no-opping TimelineMemory,
        # character_memory's relation-based mention collection, and StyleMemory) and
        # chapter_data.style_metrics always empty (silently no-opping StyleMemory entirely).
        try:
            doc = self._nlp_processor.process(cleaned_text)
            chapter_data.relations = self._extract_relations(doc, chapter_data)
            chapter_data.style_metrics = self._compute_style_metrics(doc, sentences)
        except Exception as e:
            logger.warning(f"Dependency-parsed relation/style extraction failed: {e}")

        # 5. SPECIALIZED LLM EXTRACTION STAGES — interpretation layered on top of the deterministic
        # evidence above via focused, context-aware calls (see src/pipeline/llm_extraction.py).
        # Never runs on raw text alone: always grounded in ContextRetriever's relevant-history slice
        # and the deterministic entities/coreferences/relations/dialogue just extracted.
        chapter_data.llm_delta = {}
        if self._config:
            from src.pipeline.context_retriever import ContextRetriever
            from src.pipeline.llm_extraction import LLMExtractionEngine

            # Pass the live NarrativeState directly when we have one (main.py always provides
            # it) so ContextRetriever reads memory, not disk — closing a real gap where this
            # parameter was accepted but silently never used, meaning every chapter re-read
            # narrative_state.json from disk even though the freshest state was already here.
            retriever = ContextRetriever(self._config)
            context_block, active_characters = retriever.retrieve_context(cleaned_text, current_state=current_state)

            try:
                extractor_engine = LLMExtractionEngine(self._config)
                chapter_data.llm_delta = extractor_engine.extract(
                    chapter_num=chapter_num,
                    cleaned_text=cleaned_text,
                    chapter_data=chapter_data,
                    context_block=context_block,
                )
                logger.info(f"LLM extraction stages complete for Chapter {chapter_num}.")
            except Exception as e:
                # Deterministic NLP evidence above is gathered independently of this LLM delta,
                # so a failure here degrades the chapter rather than blocking it.
                logger.warning(
                    f"LLM extraction stages unavailable for Chapter {chapter_num} ({e}). "
                    "Continuing with deterministic evidence only; no LLM-authored state delta this chapter."
                )
        else:
            logger.info(
                "No config available for LLM provider lookup. Continuing with deterministic evidence only "
                "(GLiNER/FastCoref/dependency-parse/dialogue extraction); no LLM-authored state delta or critique this chapter."
            )

        # Guarantee a consistently-shaped llm_delta even if extraction was skipped entirely above.
        if not chapter_data.llm_delta:
            chapter_data.llm_delta = {
                "character_updates": [],
                "relationship_mutations": [],
                "promises_delta": [],
                "world_updates": [],
                "timeline_events": [],
                "structural_mysteries": [],
            }

        # Apply final validation checks
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

        metrics = {
            "word_count": word_count,
            "sentence_count": len(sentences),
            "avg_sentence_length": round(avg_sentence_length, 2),
            "pos_distribution": pos_counts,
            "dialogue_density": round(dialogue_density, 4),
        }

        # Readability (textstat) \u2014 real offline readability signal instead of only raw
        # counts. The original design docs name textstat specifically as a USE-AS-IS
        # library for this; previously nothing computed it despite being listed.
        try:
            import textstat
            metrics["flesch_reading_ease"] = round(textstat.flesch_reading_ease(doc.text), 2)
            metrics["flesch_kincaid_grade"] = round(textstat.flesch_kincaid_grade(doc.text), 2)
        except Exception as e:
            logger.warning(f"textstat readability metrics unavailable: {e}")

        # Chapter-level sentiment (VADER) \u2014 real polarity signal alongside the
        # scene-level keyword-bag emotional tone in SceneEngine. VADER is lexicon-based
        # (bundled, no model download), matching the vision doc's "USE-AS-IS" framing.
        try:
            sentiment = self._get_sentiment_analyzer().polarity_scores(doc.text)
            metrics["sentiment_compound"] = round(sentiment["compound"], 4)
        except Exception as e:
            logger.warning(f"VADER sentiment scoring unavailable: {e}")

        return metrics

    def _get_sentiment_analyzer(self):
        """Lazy-load the VADER sentiment analyzer (offline, bundled lexicon)."""
        if self._sentiment_analyzer is None:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._sentiment_analyzer = SentimentIntensityAnalyzer()
        return self._sentiment_analyzer

    def _extract_relations(self, doc, chapter_data: ChapterData) -> list:
        """Extract (subject, predicate, object) evidence via dependency parsing.

        Wraps NLPProcessor.extract_subject_verb_object(), resolving pronoun
        subjects/objects to their coreference cluster's canonical mention where
        possible so downstream consumers (TimelineMemory, character mention
        collection, LLM evidence grounding) see "Laurie paced" rather than
        "he paced" whenever FastCoref already linked the two.
        """
        from src.models.state import ExtractedRelation

        pronoun_to_canonical = {}
        for cluster in getattr(chapter_data, "coreferences", []):
            # Guard against a mis-clustered or mis-picked canonical mention (FastCoref isn't
            # perfect, and _canonical_mention() just takes the first non-pronoun span in the
            # cluster): a "canonical mention" that's really a long descriptive noun phrase (e.g.
            # "the servant's passage behind the bookshelf") is a sign the cluster or the pick is
            # wrong, not a usable substitute for "he"/"she". Skip substitution in that case rather
            # than propagate the error into every relation touching that pronoun.
            if not cluster.canonical_mention or len(cluster.canonical_mention.split()) > 4:
                continue
            for mention in cluster.mentions:
                pronoun_to_canonical[mention.strip().lower()] = cluster.canonical_mention

        def resolve(text: str) -> str:
            return pronoun_to_canonical.get(text.strip().lower(), text)

        relations = []
        seen = set()
        for triple in self._nlp_processor.extract_subject_verb_object(doc):
            subject = resolve(triple["subject"]).strip()
            obj = resolve(triple["object"]).strip()
            predicate = triple["verb"].strip()
            if not subject or not predicate or not obj:
                continue
            if subject.lower() in ("it", "this", "that", "there") or obj.lower() in ("it", "this", "that", "there"):
                continue
            # Skip subjects/objects that are long noun phrases rather than entity-like mentions —
            # keeps relation evidence (and everything downstream: character mention collection,
            # TimelineMemory, the LLM evidence block) focused on names/short referents.
            if len(subject.split()) > 5 or len(obj.split()) > 5:
                continue
            dedup_key = (subject.lower(), predicate.lower(), obj.lower())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            relations.append(ExtractedRelation(
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=0.7,
                source="spacy_dependency",
            ))
        return relations

    def _serialize_state(self, state: Optional[NarrativeState]) -> str:
        if state is None:
            return "No existing state."
        
        # Serialize characters
        char_lines = []
        for cid, fields in state.characters.items():
            name = fields.get("canonical_name").current.value if fields.get("canonical_name") and fields.get("canonical_name").current else cid
            aliases = fields.get("aliases").current.value if fields.get("aliases") and fields.get("aliases").current else []
            loc = fields.get("location").current.value if fields.get("location") and fields.get("location").current else "unknown"
            inv = fields.get("inventory").current.value if fields.get("inventory") and fields.get("inventory").current else []
            goals = fields.get("goals").current.value if fields.get("goals") and fields.get("goals").current else []
            fears = fields.get("fears").current.value if fields.get("fears") and fields.get("fears").current else []
            
            # Traits
            traits = {}
            for k, entry in fields.items():
                if k.startswith("physical_") or k == "personality_traits":
                    if entry and entry.current:
                        traits[k] = entry.current.value
                        
            char_lines.append(
                f"- Character ID: {cid}\n"
                f"  Name: {name}\n"
                f"  Aliases: {aliases}\n"
                f"  Location: {loc}\n"
                f"  Inventory: {inv}\n"
                f"  Goals: {goals}\n"
                f"  Fears: {fears}\n"
                f"  Traits: {traits}"
            )
            
        # Serialize relationships
        rel_lines = []
        for rid, fields in state.relationships.items():
            label = fields.get("relationship_label").current.value if fields.get("relationship_label") and fields.get("relationship_label").current else "unknown"
            char_parts = rid.split("::")
            rel_lines.append(f"- {char_parts[0]} and {char_parts[1]}: Stance: {label}")
            
        # Serialize world
        world_lines = []
        for wid, fields in state.world.items():
            loc = fields.get("location").current.value if fields.get("location") and fields.get("location").current else None
            owner = fields.get("owner").current.value if fields.get("owner") and fields.get("owner").current else None
            world_lines.append(f"- World Item/Place: {wid} (Location: {loc}, Owner: {owner})")
            
        # Serialize promises
        promise_lines = []
        for pid, fields in state.promises.items():
            text = fields.get("promise_text").current.value if fields.get("promise_text") and fields.get("promise_text").current else ""
            status = fields.get("status").current.value if fields.get("status") and fields.get("status").current else "OPEN"
            speaker = fields.get("speaker_id").current.value if fields.get("speaker_id") and fields.get("speaker_id").current else "unknown"
            listener = fields.get("listener_id").current.value if fields.get("listener_id") and fields.get("listener_id").current else "unknown"
            promise_lines.append(f"- Promise: {text} from {speaker} to {listener} (Status: {status})")

        return (
            "Characters:\n" + ("\n".join(char_lines) if char_lines else "None") + "\n\n"
            "Relationships:\n" + ("\n".join(rel_lines) if rel_lines else "None") + "\n\n"
            "World Lore:\n" + ("\n".join(world_lines) if world_lines else "None") + "\n\n"
            "Promises:\n" + ("\n".join(promise_lines) if promise_lines else "None")
        )

