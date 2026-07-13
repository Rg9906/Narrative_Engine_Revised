"""Unit tests for Narrative Intelligence Engine memory modules."""

import pytest
from pathlib import Path
from src.models.state import ChapterData, ExtractedEntity, ExtractedDialogue, ExtractedRelation, TextSpan
from src.memory.character_memory import CharacterMemory
from src.memory.relationship_memory import RelationshipMemory
from src.memory.world_memory import WorldMemory
from src.memory.timeline_memory import TimelineMemory
from src.memory.theme_memory import ThemeMemory
from src.memory.promise_memory import PromiseMemory
from src.memory.mystery_memory import MysteryMemory


@pytest.fixture
def empty_chapter_data():
    return ChapterData(
        chapter_number=1,
        source_name="test.txt",
        chapter_title="Test Chapter",
        raw_text="Alice was here. She loved Bob.",
        paragraphs=["Alice was here. She loved Bob."],
        sentences=["Alice was here.", "She loved Bob."],
    )


class TestCharacterMemory:
    def test_update_from_chapter_adds_character(self, empty_chapter_data):
        empty_chapter_data.entities = [
            ExtractedEntity(text="Alice", label="person", confidence=1.0)
        ]
        memory = CharacterMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        assert len(changes) > 0
        assert "alice" in memory.entries
        assert memory.get_entry("alice", "canonical_name").current.value == "Alice"
        assert memory.get_entry("alice", "mention_count").current.value == 1

    def test_update_from_chapter_increments_mention_count(self, empty_chapter_data):
        empty_chapter_data.entities = [
            ExtractedEntity(text="Alice", label="person", confidence=1.0)
        ]
        memory = CharacterMemory()
        memory.update_from_chapter(empty_chapter_data, 1)
        # Second mention
        memory.update_from_chapter(empty_chapter_data, 1)

        assert memory.get_entry("alice", "mention_count").current.value == 2


class TestRelationshipMemory:
    def test_relationship_created_from_svo(self, empty_chapter_data):
        empty_chapter_data.relations = [
            ExtractedRelation(subject="Alice", predicate="loved", object="Bob", confidence=1.0)
        ]
        memory = RelationshipMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        assert len(changes) > 0
        # The key is direction-agnostic
        assert "alice::bob" in memory.entries or "bob::alice" in memory.entries
        key = "alice::bob" if "alice::bob" in memory.entries else "bob::alice"
        assert memory.get_entry(key, "relationship_label").current.value == "ROMANTIC"


class TestWorldMemory:
    def test_world_elements_added(self, empty_chapter_data):
        empty_chapter_data.entities = [
            ExtractedEntity(text="Thornfield Hall", label="location", confidence=1.0),
            ExtractedEntity(text="Sword of Truth", label="object", confidence=1.0)
        ]
        memory = WorldMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        assert len(changes) > 0
        assert "thornfield_hall" in memory.entries
        assert "sword_of_truth" in memory.entries
        assert memory.get_entry("thornfield_hall", "type").current.value == "location"
        assert memory.get_entry("sword_of_truth", "type").current.value == "object"


class TestThemeMemory:
    def test_theme_and_symbol_detection(self, empty_chapter_data):
        # Text containing love (theme) and fire (symbol)
        empty_chapter_data.raw_text = "Their love burned like fire."
        memory = ThemeMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        assert len(changes) > 0
        assert "theme_love" in memory.entries
        assert "symbol_fire" in memory.entries
        assert memory.get_entry("theme_love", "mention_count").current.value > 0
        assert memory.get_entry("symbol_fire", "mention_count").current.value > 0


class TestPromiseMemory:
    def test_promise_extracted_and_resolved(self, empty_chapter_data):
        # Chapter 1: promise made
        ch1_data = ChapterData(
            chapter_number=1,
            source_name="test.txt",
            chapter_title="Chapter 1",
            raw_text="I promise to return.",
            paragraphs=["I promise to return."],
            sentences=["I promise to return."],
        )
        memory = PromiseMemory()
        memory.update_from_chapter(ch1_data, 1)
        unresolved = memory.get_unresolved_promises()
        assert len(unresolved) == 1
        assert "I promise to return." in unresolved[0]["text"]

        # Chapter 2: promise resolved (fulfilled)
        ch2_data = ChapterData(
            chapter_number=2,
            source_name="test.txt",
            chapter_title="Chapter 2",
            raw_text="Finally, the vow was fulfilled.",
            paragraphs=["Finally, the vow was fulfilled."],
            sentences=["Finally, the vow was fulfilled."],
        )
        memory.update_from_chapter(ch2_data, 2)
        unresolved_after = memory.get_unresolved_promises()
        assert len(unresolved_after) == 0


class TestMysteryMemory:
    def test_mystery_extracted_and_revelation(self, empty_chapter_data):
        # Chapter 1: mystery introduced
        ch1_data = ChapterData(
            chapter_number=1,
            source_name="test.txt",
            chapter_title="Chapter 1",
            raw_text="Why did he leave?",
            paragraphs=["Why did he leave?"],
            sentences=["Why did he leave?"],
        )
        memory = MysteryMemory()
        memory.update_from_chapter(ch1_data, 1)
        unresolved = memory.get_unresolved_mysteries()
        assert len(unresolved) == 1
        assert "Why did he leave?" in unresolved[0]["text"]

        # Chapter 2: mystery resolved
        ch2_data = ChapterData(
            chapter_number=2,
            source_name="test.txt",
            chapter_title="Chapter 2",
            raw_text="The truth was finally revealed.",
            paragraphs=["The truth was finally revealed."],
            sentences=["The truth was finally revealed."],
        )
        memory.update_from_chapter(ch2_data, 2)
        unresolved_after = memory.get_unresolved_mysteries()
        assert len(unresolved_after) == 0
