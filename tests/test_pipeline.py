"""
Tests for the NLP Pipeline — Evidence Extraction Layer.

These tests verify that the pipeline correctly extracts raw evidence
from text. They do NOT test narrative understanding (that's the
Narrative State Engine's job).
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.parser import DocumentParser
from src.pipeline.pipeline import Pipeline
from src.pipeline.ner import EntityExtractor
from src.pipeline.coref import CoreferenceResolver
from src.pipeline.dialogue import DialogueExtractor
from src.models.state import (
    ChapterData,
    ExtractedCoreferenceCluster,
    ExtractedEntity,
    ExtractedRelation,
    TextSpan,
)


# =============================================================================
# Test Data Paths
# =============================================================================

TEST_DATA_DIR = Path(__file__).parent / "data"
EXAMPLE_CHAPTER_TXT = TEST_DATA_DIR / "example_chapter.txt"


# =============================================================================
# DocumentParser Tests
# =============================================================================

class TestDocumentParser:
    """Tests for the DocumentParser class."""

    def setup_method(self):
        """Create a fresh parser for each test."""
        self.parser = DocumentParser()

    # --- TXT parsing ---

    def test_parse_txt_returns_string(self):
        """Parser should return a non-empty string from a TXT file."""
        text = self.parser.parse(str(EXAMPLE_CHAPTER_TXT))
        assert isinstance(text, str)
        assert len(text) > 0

    def test_parse_txt_contains_expected_content(self):
        """Parsed text should contain known phrases from the test chapter."""
        text = self.parser.parse(str(EXAMPLE_CHAPTER_TXT))
        assert "Alice" in text
        assert "Thomas" in text
        assert "Silver Gate" in text
        assert "Thornfield Hall" in text
        assert "The Copper Bell" in text

    def test_parse_txt_preserves_structure(self):
        """Parser should preserve paragraph structure (newlines)."""
        text = self.parser.parse(str(EXAMPLE_CHAPTER_TXT))
        # The chapter has multiple paragraphs separated by blank lines
        assert "\n" in text

    # --- Error handling ---

    def test_parse_nonexistent_file_raises(self):
        """Parser should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            self.parser.parse("nonexistent_file.txt")

    def test_parse_unsupported_format_raises(self):
        """Parser should raise ValueError for unsupported file formats."""
        # Create a temp file with unsupported extension
        temp_path = TEST_DATA_DIR / "temp_test.xyz"
        temp_path.write_text("test", encoding="utf-8")
        try:
            with pytest.raises(ValueError, match="Unsupported file format"):
                self.parser.parse(str(temp_path))
        finally:
            temp_path.unlink()

    # --- File info ---

    def test_get_file_info(self):
        """get_file_info should return correct metadata."""
        info = self.parser.get_file_info(str(EXAMPLE_CHAPTER_TXT))
        assert info["exists"] is True
        assert info["extension"] == ".txt"
        assert info["supported"] is True
        assert info["size_bytes"] > 0
        assert info["name"] == "example_chapter.txt"

    def test_get_file_info_nonexistent(self):
        """get_file_info should report non-existent files correctly."""
        info = self.parser.get_file_info("does_not_exist.pdf")
        assert info["exists"] is False


# =============================================================================
# Core Data Model Tests
# =============================================================================

class TestCoreModels:
    """Tests for the core data models — the DNA of the project."""

    def test_evidence_creation_and_serialization(self):
        """Evidence should serialize and deserialize correctly."""
        from src.models.state import Evidence, EvidenceType, TextSpan

        evidence = Evidence(
            text_span=TextSpan(text="Alice had blue eyes", start_char=0, end_char=19),
            evidence_type=EvidenceType.DIRECT_STATEMENT,
            source_chapter=1,
            source_scene=1,
            confidence=0.95,
            related_entities=["alice"],
            interpretation_hint="Physical description of protagonist",
        )

        # Serialize
        data = evidence.to_dict()
        assert data["evidence_type"] == "DIRECT_STATEMENT"
        assert data["source_chapter"] == 1
        assert data["confidence"] == 0.95

        # Deserialize
        restored = Evidence.from_dict(data)
        assert restored.text_span.text == "Alice had blue eyes"
        assert restored.evidence_type == EvidenceType.DIRECT_STATEMENT
        assert restored.related_entities == ["alice"]

    def test_state_entry_evolution(self):
        """StateEntry should preserve history when updated — never overwrite."""
        from src.models.state import StateEntry, StateSnapshot, NarrativeElementType

        entry = StateEntry(
            key="emotional_state",
            element_type=NarrativeElementType.CHARACTER,
        )

        # First state: optimistic (chapter 1)
        entry.update(StateSnapshot(
            value="optimistic",
            chapter=1,
            confidence=0.9,
            reasoning="Narration describes Alice as hopeful about her journey",
        ))
        assert entry.current.value == "optimistic"
        assert len(entry.history) == 0
        assert entry.version == 2  # started at 1, incremented

        # Second state: sad (chapter 3) — history should be preserved
        entry.update(StateSnapshot(
            value="sad",
            chapter=3,
            confidence=0.85,
            reasoning="Alice watches door after brother's departure",
        ))
        assert entry.current.value == "sad"
        assert len(entry.history) == 1
        assert entry.history[0].value == "optimistic"
        assert entry.version == 3

        # Trajectory should show full evolution
        trajectory = entry.get_trajectory()
        assert len(trajectory) == 2
        assert trajectory[0].value == "optimistic"
        assert trajectory[1].value == "sad"

    def test_state_entry_dormancy_tracking(self):
        """StateEntry should track how long since last mention."""
        from src.models.state import StateEntry, StateSnapshot

        entry = StateEntry(key="test")
        entry.update(StateSnapshot(value="active", chapter=5))

        assert entry.chapters_since_last_mention(5) == 0
        assert entry.chapters_since_last_mention(10) == 5
        assert entry.chapters_since_last_mention(20) == 15

    def test_narrative_state_initialization(self):
        """Fresh NarrativeState should be empty but valid."""
        from src.models.state import NarrativeState

        state = NarrativeState()
        assert state.last_processed_chapter == 0
        assert state.total_chapters_processed == 0
        assert len(state.characters) == 0
        assert len(state.relationships) == 0
        assert len(state.evidence_store) == 0

    def test_narrative_state_serialization_roundtrip(self):
        """NarrativeState should survive a full serialize/deserialize cycle."""
        from src.models.state import (
            NarrativeState, Evidence, EvidenceType, TextSpan,
            StateEntry, StateSnapshot, NarrativeElementType,
        )

        # Build a state with some content
        state = NarrativeState()

        # Add evidence
        ev = Evidence(
            text_span=TextSpan(text="test", start_char=0, end_char=4),
            evidence_type=EvidenceType.DIALOGUE,
            source_chapter=1,
        )
        state.add_evidence(ev)

        # Add a character
        alice_mood = StateEntry(
            key="mood",
            element_type=NarrativeElementType.CHARACTER,
        )
        alice_mood.update(StateSnapshot(
            value="optimistic", chapter=1, evidence_ids=[ev.id],
        ))
        state.characters["alice"] = {"mood": alice_mood}

        # Serialize and deserialize
        data = state.to_dict()
        restored = NarrativeState.from_dict(data)

        assert restored.characters["alice"]["mood"].current.value == "optimistic"
        assert len(restored.evidence_store) == 1
        assert ev.id in restored.evidence_store

    def test_state_delta_categorization(self):
        """StateDelta should correctly categorize changes by type."""
        from src.models.state import (
            StateDelta, StateChange, StateChangeType, NarrativeElementType,
        )

        delta = StateDelta(chapter_number=5)
        delta.changes = [
            StateChange(
                change_type=StateChangeType.INTRODUCTION,
                target_type=NarrativeElementType.CHARACTER,
                target_id="bob",
                field_key="introduction",
                new_value="Bob appears for the first time",
            ),
            StateChange(
                change_type=StateChangeType.EVOLUTION,
                target_type=NarrativeElementType.CHARACTER,
                target_id="alice",
                field_key="mood",
                old_value="optimistic",
                new_value="worried",
            ),
            StateChange(
                change_type=StateChangeType.CONTRADICTION,
                target_type=NarrativeElementType.CHARACTER,
                target_id="alice",
                field_key="eye_color",
                old_value="blue",
                new_value="green",
            ),
        ]

        assert len(delta.introductions) == 1
        assert len(delta.evolutions) == 1
        assert len(delta.contradictions) == 1
        assert delta.introductions[0].target_id == "bob"
        assert delta.contradictions[0].old_value == "blue"


# =============================================================================
# Phase 4 Tests: GLiNER and FastCoref Integration
# =============================================================================

class TestEntityExtractor:
    """Tests for the GLiNER wrapper without loading the real model."""

    def test_extract_maps_gliner_output_to_entities_with_spans(self):
        """EntityExtractor should preserve labels, scores, and offsets."""

        class FakeGLiNERModel:
            def predict_entities(self, text, labels, threshold):
                assert "person" in labels
                assert threshold == 0.42
                return [
                    {
                        "text": "Alice",
                        "label": "person",
                        "start": 0,
                        "end": 5,
                        "score": 0.98,
                    },
                    {
                        "text": "Silver Gate",
                        "label": "location",
                        "start": 20,
                        "end": 31,
                        "score": 0.91,
                    },
                ]

        extractor = EntityExtractor(threshold=0.42)
        extractor._model = FakeGLiNERModel()

        entities = extractor.extract(
            "Alice walked to the Silver Gate.",
            labels=["person", "location"],
        )

        assert len(entities) == 2
        assert entities[0].text == "Alice"
        assert entities[0].label == "person"
        assert entities[0].confidence == 0.98
        assert entities[0].span.start_char == 0
        assert entities[0].span.end_char == 5


class TestCoreferenceResolver:
    """Tests for the FastCoref wrapper without loading the real model."""

    def test_resolve_maps_fastcoref_clusters_to_structured_evidence(self):
        """CoreferenceResolver should produce canonical structured clusters."""

        class FakePrediction:
            def get_clusters(self):
                return [["Alice", "She"], ["Thomas", "her younger brother", "He"]]

        class FakeFastCorefModel:
            def predict(self, texts):
                assert texts == ["Alice left. She was worried."]
                return [FakePrediction()]

        resolver = CoreferenceResolver()
        resolver._model = FakeFastCorefModel()

        clusters = resolver.resolve("Alice left. She was worried.")

        assert clusters == [
            ExtractedCoreferenceCluster(
                mentions=["Alice", "She"],
                canonical_mention="Alice",
            ),
            ExtractedCoreferenceCluster(
                mentions=["Thomas", "her younger brother", "He"],
                canonical_mention="Thomas",
            ),
        ]

    def test_canonical_mention_falls_back_when_cluster_is_only_pronouns(self):
        """Pronoun-only clusters should still get a stable representative."""
        resolver = CoreferenceResolver()
        assert resolver._canonical_mention(["she", "her"]) == "she"


class TestPhase4PipelineIntegration:
    """Integration tests for Phase 4 evidence in Pipeline.process_chapter."""

    def test_pipeline_populates_entities_and_coreferences(self):
        """Pipeline should attach GLiNER and FastCoref evidence to ChapterData."""

        class FakeEntityExtractor:
            def extract(self, text, labels=None):
                assert "Alice" in text
                assert "person" in labels
                return [
                    ExtractedEntity(
                        text="Alice",
                        label="person",
                        span=TextSpan(text="Alice", start_char=0, end_char=5),
                        confidence=0.99,
                    ),
                    ExtractedEntity(
                        text="Silver Gate",
                        label="location",
                        span=TextSpan(text="Silver Gate", start_char=24, end_char=35),
                        confidence=0.9,
                    ),
                ]

        class FakeCoreferenceResolver:
            def resolve(self, text):
                assert "She" in text
                return [
                    ExtractedCoreferenceCluster(
                        mentions=["Alice", "She"],
                        canonical_mention="Alice",
                        confidence=0.88,
                    )
                ]

        pipeline = Pipeline(
            entity_extractor=FakeEntityExtractor(),
            coreference_resolver=FakeCoreferenceResolver(),
        )

        chapter_data = pipeline.process_chapter(
            "Alice walked to the Silver Gate. She carried the journal.",
            chapter_num=4,
            is_file=False,
        )

        assert chapter_data.chapter_number == 4
        assert [entity.text for entity in chapter_data.entities] == ["Alice", "Silver Gate"]
        assert chapter_data.entities[0].coreference_cluster == 0
        assert chapter_data.entities[1].coreference_cluster is None
        assert chapter_data.coreference_clusters == [["Alice", "She"]]
        assert chapter_data.coreferences[0].canonical_mention == "Alice"

        serialized = chapter_data.to_dict()
        assert serialized["entity_count"] == 2
        assert serialized["entities"][0]["span"]["start_char"] == 0
        assert serialized["entities"][0]["coreference_cluster"] == 0
        assert serialized["coreferences"][0]["mentions"] == ["Alice", "She"]


# =============================================================================
# Phase 5 Tests: Canonical ChapterData Evidence Package
# =============================================================================

class TestDialogueExtractor:
    """Tests for chapter-local dialogue evidence extraction."""

    def test_extracts_dialogue_with_speaker_after_quote(self):
        extractor = DialogueExtractor()
        text = '"You do not have to go," said Thomas. Alice shook her head.'

        dialogues = extractor.extract(text)

        assert len(dialogues) == 1
        assert dialogues[0].text == "You do not have to go,"
        assert dialogues[0].speaker == "Thomas"
        assert dialogues[0].confidence == 0.8
        assert dialogues[0].attribution_method == "speech_tag_after"
        assert dialogues[0].span.start_char == 0

    def test_unattributed_dialogue_is_marked_unknown(self):
        extractor = DialogueExtractor()

        dialogues = extractor.extract('"The Gate is not a door."')

        assert len(dialogues) == 1
        assert dialogues[0].speaker == "Unknown"
        assert dialogues[0].confidence == 0.25
        assert dialogues[0].attribution_method == "unattributed_quote"


class TestChapterDataEvidencePackage:
    """Tests for ChapterData organization and validation."""

    def test_validate_flags_missing_evidence_structure(self):
        chapter_data = ChapterData(chapter_number=0, raw_text="Alice walked.")

        warnings = chapter_data.validate()

        assert "chapter_number should be >= 1" in warnings
        assert "raw_text is present but no sentences were extracted" in warnings
        assert "raw_text is present but no paragraphs were extracted" in warnings

    def test_to_dict_includes_complete_evidence_package(self):
        chapter_data = ChapterData(
            chapter_number=2,
            source_name="chapter_02.txt",
            chapter_title="Chapter 2: The Warning",
            raw_text="Chapter 2: The Warning\n\nAlice listened.",
            paragraphs=["Chapter 2: The Warning", "Alice listened."],
            sentences=["Chapter 2: The Warning", "Alice listened."],
            entities=[
                ExtractedEntity(
                    text="Alice",
                    label="person",
                    normalized_text="alice",
                    source="gliner",
                    span=TextSpan("Alice", 24, 29, 1),
                )
            ],
            relations=[
                ExtractedRelation(
                    subject="Alice",
                    predicate="listened",
                    object="warning",
                    span=TextSpan("Alice listened.", 24, 39, 1),
                    source="spacy_svo",
                )
            ],
        )
        chapter_data.validate()

        data = chapter_data.to_dict()

        assert data["chapter_title"] == "Chapter 2: The Warning"
        assert data["paragraph_count"] == 2
        assert data["sentences"] == ["Chapter 2: The Warning", "Alice listened."]
        assert data["entities"][0]["normalized_text"] == "alice"
        assert data["relations"][0]["span"]["sentence_index"] == 1
        assert data["evidence_summary"]["entities"] == 1
        assert data["validation_warnings"] == []


class TestPhase5PipelineIntegration:
    """Integration tests for canonical ChapterData output."""

    def test_pipeline_outputs_organized_validated_chapter_data(self):
        class FakeEntityExtractor:
            def extract(self, text, labels=None):
                return [
                    ExtractedEntity(
                        text="Alice",
                        label="person",
                        span=TextSpan(text="Alice", start_char=text.index("Alice"), end_char=text.index("Alice") + 5),
                        confidence=0.99,
                    ),
                    ExtractedEntity(
                        text="Thomas",
                        label="person",
                        span=TextSpan(text="Thomas", start_char=text.index("Thomas"), end_char=text.index("Thomas") + 6),
                        confidence=0.97,
                    ),
                ]

        class FakeCoreferenceResolver:
            def resolve(self, text):
                return [
                    ExtractedCoreferenceCluster(
                        mentions=["Alice", "She"],
                        canonical_mention="Alice",
                        confidence=0.9,
                    )
                ]

        sample = (
            "Chapter 5: The Crossing\n\n"
            "Alice stood at the bridge. \"Wait for me,\" said Thomas.\n\n"
            "She tightened the strap on her satchel and stepped forward."
        )
        pipeline = Pipeline(
            entity_extractor=FakeEntityExtractor(),
            coreference_resolver=FakeCoreferenceResolver(),
        )

        chapter_data = pipeline.process_chapter(sample, chapter_num=5, is_file=False)
        data = chapter_data.to_dict()

        assert chapter_data.chapter_title == "Chapter 5: The Crossing"
        assert chapter_data.paragraphs == [
            "Chapter 5: The Crossing",
            'Alice stood at the bridge. "Wait for me," said Thomas.',
            "She tightened the strap on her satchel and stepped forward.",
        ]
        assert chapter_data.entities[0].normalized_text == "alice"
        assert chapter_data.entities[0].source == "gliner"
        assert chapter_data.coreferences[0].cluster_id == 0
        assert chapter_data.coreferences[0].source == "fastcoref"
        assert chapter_data.dialogues[0].speaker == "Thomas"
        assert chapter_data.validation_warnings == []
        assert data["evidence_summary"]["paragraphs"] == 3
        assert data["evidence_summary"]["dialogues"] == 1
