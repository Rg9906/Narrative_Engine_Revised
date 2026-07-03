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
