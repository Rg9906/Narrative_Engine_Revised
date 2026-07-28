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
from src.memory.style_memory import StyleMemory


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

    def test_physical_trait_extracts_real_descriptor_not_adjacent_word(self):
        # Regression test: _extract_trait_value used to grab whatever word sat next to
        # the matched keyword regardless of part of speech, producing nonsense values
        # like physical_eye_color="his" from "His eyes were tired." Anchor nouns
        # ("eyes", "hair") with no accompanying descriptor must not fabricate a value;
        # when a real descriptor IS present, that word must be the one extracted.
        cd = ChapterData(
            chapter_number=1,
            raw_text="Alice appeared. Alice's blue eyes sparkled. Bob's eyes were tired.",
            sentences=["Alice appeared.", "Alice's blue eyes sparkled.", "Bob's eyes were tired."],
            entities=[
                ExtractedEntity(text="Alice", label="person", confidence=1.0),
                ExtractedEntity(text="Bob", label="person", confidence=1.0),
            ],
        )
        memory = CharacterMemory()
        memory.update_from_chapter(cd, 1)
        memory.extract_advanced_attributes(cd, 1)

        eye_color = memory.get_entry("alice", "physical_eye_color")
        assert eye_color is not None and eye_color.current.value == "blue"

        # Bob's sentence has the anchor noun ("eyes") but no real descriptor ("tired" is
        # not a color) -- must NOT fabricate a value from an adjacent word ("were", "s").
        bob_eye_color = memory.get_entry("bob", "physical_eye_color")
        assert bob_eye_color is None


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

    def test_object_containment_in_object(self, empty_chapter_data):
        empty_chapter_data.raw_text = "The Emperor's Scarab was hidden within the Obsidian Sarcophagus."
        empty_chapter_data.sentences = ["The Emperor's Scarab was hidden within the Obsidian Sarcophagus."]
        from src.models.state import TextSpan
        empty_chapter_data.entities = [
            ExtractedEntity(
                text="Emperor's Scarab",
                label="object",
                span=TextSpan(text="Emperor's Scarab", start_char=4, end_char=20, sentence_index=0),
                confidence=1.0
            ),
            ExtractedEntity(
                text="Obsidian Sarcophagus",
                label="object",
                span=TextSpan(text="Obsidian Sarcophagus", start_char=43, end_char=63, sentence_index=0),
                confidence=1.0
            )
        ]
        memory = WorldMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        # Locate the change representing containment
        loc_changes = [c for c in changes if c.field_key == "location"]
        assert len(loc_changes) > 0
        assert loc_changes[0].new_value == "obsidian_sarcophagus"
        
        scarab_entry = memory.get_entry("emperor_s_scarab", "location")
        assert scarab_entry is not None
        assert scarab_entry.current.value == "obsidian_sarcophagus"


class TestThemeMemory:
    def test_theme_and_symbol_detection(self, empty_chapter_data):
        # keyword_count counts DISTINCT keywords from the category present in the
        # chapter (not occurrences of one keyword) — so a brand-new theme/symbol now
        # requires >=2 distinct keywords from its list (MIN_MENTIONS_TO_INTRODUCE) to
        # be introduced. "heart"+"love" both belong to THEME_KEYWORDS["love"];
        # "fire"+"flame" (+"burn" via "burned") both belong to SYMBOL_KEYWORDS["fire"].
        empty_chapter_data.raw_text = "Their heart burned with love, glowing like fire and flame."
        memory = ThemeMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        assert len(changes) > 0
        assert "theme_love" in memory.entries
        assert "symbol_fire" in memory.entries
        assert memory.get_entry("theme_love", "mention_count").current.value > 0
        assert memory.get_entry("symbol_fire", "mention_count").current.value > 0

    def test_single_incidental_mention_does_not_introduce_theme(self, empty_chapter_data):
        # A single passing mention of a theme/symbol keyword should NOT permanently
        # register that category — this was the main source of noise (every one of
        # 15 theme + 10 symbol categories firing within a couple of chapters).
        empty_chapter_data.raw_text = "She felt a flicker of love, but said nothing more."
        memory = ThemeMemory()
        memory.update_from_chapter(empty_chapter_data, 1)

        assert "theme_love" not in memory.entries


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


class TestStyleMemory:
    def test_style_metrics_tracked_and_updated(self, empty_chapter_data):
        empty_chapter_data.style_metrics = {
            "word_count": 1000,
            "sentence_count": 50,
            "avg_sentence_length": 20.0,
            "dialogue_density": 0.15,
        }
        memory = StyleMemory()
        changes = memory.update_from_chapter(empty_chapter_data, 1)

        assert len(changes) > 0
        assert "global_style" in memory.entries
        assert memory.get_entry("global_style", "word_count").current.value == 1000
        assert memory.get_entry("global_style", "avg_sentence_length").current.value == 20.0

        # Update with new chapter data to test evolution
        empty_chapter_data.style_metrics = {
            "word_count": 1200,
            "sentence_count": 60,
            "avg_sentence_length": 20.0,
            "dialogue_density": 0.20,
        }
        changes_ch2 = memory.update_from_chapter(empty_chapter_data, 2)
        assert len(changes_ch2) > 0
        word_count_entry = memory.get_entry("global_style", "word_count")
        assert word_count_entry.current.value == 1200
        assert len(word_count_entry.history) == 1
        assert word_count_entry.history[0].value == 1000


def test_stable_hash():
    from src.utils import stable_hash
    # Test determinism
    h1 = stable_hash("test string")
    h2 = stable_hash("test string")
    assert h1 == h2
    assert len(h1) == 16
    # Test stability of outputs (MD5 prefix of 'test string')
    assert h1 == "6f8db599de986fab"
    # Test empty string behavior
    assert stable_hash("") == ""
    assert stable_hash(None) == ""


def test_promise_and_mystery_id_determinism(empty_chapter_data):
    # Tests that IDs generated are completely deterministic across restarts
    ch_data = ChapterData(
        chapter_number=1,
        source_name="test.txt",
        chapter_title="Chapter 1",
        raw_text="Why did he leave? I promise to return.",
        paragraphs=["Why did he leave? I promise to return."],
        sentences=["Why did he leave?", "I promise to return."],
    )
    
    # Process with mystery memory
    memory_myst = MysteryMemory()
    memory_myst.update_from_chapter(ch_data, 1)
    unresolved_myst = memory_myst.get_unresolved_mysteries()
    assert len(unresolved_myst) == 1
    myst_id = unresolved_myst[0]["id"]
    
    # Process again with a new memory instance (simulating reload/new run)
    memory_myst2 = MysteryMemory()
    memory_myst2.update_from_chapter(ch_data, 1)
    unresolved_myst2 = memory_myst2.get_unresolved_mysteries()
    assert len(unresolved_myst2) == 1
    myst_id2 = unresolved_myst2[0]["id"]
    
    assert myst_id == myst_id2
    
    # Process with promise memory
    memory_prom = PromiseMemory()
    memory_prom.update_from_chapter(ch_data, 1)
    unresolved_prom = memory_prom.get_unresolved_promises()
    assert len(unresolved_prom) == 1
    prom_id = unresolved_prom[0]["id"]
    
    # Process again with a new promise memory instance
    memory_prom2 = PromiseMemory()
    memory_prom2.update_from_chapter(ch_data, 1)
    unresolved_prom2 = memory_prom2.get_unresolved_promises()
    assert len(unresolved_prom2) == 1
    prom_id2 = unresolved_prom2[0]["id"]
    
    assert prom_id == prom_id2


def test_promise_enriched_fields_and_semantic_resolution():
    ch1_data = ChapterData(
        chapter_number=1,
        source_name="test.txt",
        chapter_title="Chapter 1",
        raw_text="I promise to return.",
        paragraphs=["I promise to return."],
        sentences=["I promise to return."],
    )
    ch1_data.entities = [
        ExtractedEntity(text="Arthur", label="person", confidence=1.0),
        ExtractedEntity(text="Merlin", label="person", confidence=1.0)
    ]
    ch1_data.dialogues = [
        ExtractedDialogue(speaker="Arthur", text="I promise to return.", confidence=1.0)
    ]
    
    memory = PromiseMemory()
    memory.update_from_chapter(ch1_data, 1)
    unresolved = memory.get_unresolved_promises()
    
    assert len(unresolved) == 1
    assert unresolved[0]["speaker"] == "arthur"
    assert unresolved[0]["listener_id"] == "merlin"
    assert unresolved[0]["climax_proximity_threshold"] == 3
    assert unresolved[0]["status"] == "OPEN"

    # Chapter 2: semantic resolution without resolution keywords
    ch2_data = ChapterData(
        chapter_number=2,
        source_name="test.txt",
        chapter_title="Chapter 2",
        raw_text="Arthur kept his word and decided to return to Merlin.",
        paragraphs=["Arthur kept his word and decided to return to Merlin."],
        sentences=["Arthur kept his word and decided to return to Merlin."],
    )
    memory.update_from_chapter(ch2_data, 2)
    unresolved_after = memory.get_unresolved_promises()
    assert len(unresolved_after) == 0


def test_alias_overlap_auto_merge():
    memory = CharacterMemory()
    ch1_data = ChapterData(
        chapter_number=1,
        source_name="test.txt",
        chapter_title="Chapter 1",
        raw_text="Arthur was here.",
        paragraphs=["Arthur was here."],
        sentences=["Arthur was here."],
    )
    ch1_data.entities = [ExtractedEntity(text="Arthur", label="person", confidence=1.0)]
    memory.update_from_chapter(ch1_data, 1)
    
    # Mention "Arthur Pendragon" should auto-merge to "arthur"
    ch2_data = ChapterData(
        chapter_number=2,
        source_name="test.txt",
        chapter_title="Chapter 2",
        raw_text="Arthur Pendragon was here.",
        paragraphs=["Arthur Pendragon was here."],
        sentences=["Arthur Pendragon was here."],
    )
    ch2_data.entities = [ExtractedEntity(text="Arthur Pendragon", label="person", confidence=1.0)]
    changes = memory.update_from_chapter(ch2_data, 2)
    
    assert "arthur" in memory.entries
    assert "arthur_pendragon" not in memory.entries


def test_inventory_extraction():
    memory = CharacterMemory()
    ch1_data = ChapterData(
        chapter_number=1,
        source_name="test.txt",
        chapter_title="Chapter 1",
        raw_text="Arthur took the sword.",
        paragraphs=["Arthur took the sword."],
        sentences=["Arthur took the sword."],
    )
    ch1_data.entities = [
        ExtractedEntity(text="Arthur", label="person", confidence=1.0),
        ExtractedEntity(text="sword", label="object", confidence=1.0)
    ]
    
    # Set canonical name first
    memory.update_from_chapter(ch1_data, 1)
    memory.extract_advanced_attributes(ch1_data, 1)
    
    inv = memory.get_entry("arthur", "inventory")
    assert inv is not None
    assert "sword" in inv.current.value



