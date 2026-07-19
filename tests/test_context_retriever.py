import json
import shutil
from pathlib import Path
import pytest
from src.pipeline.context_retriever import ContextRetriever

class DummyConfig:
    def __init__(self, memory_dir):
        self.memory_dir = Path(memory_dir)
        self.data_dir = self.memory_dir.parent
        self.profiles_dir = self.data_dir / "profiles"
        self.relationships_dir = self.data_dir / "relationships"
        self.clues_dir = self.data_dir / "clues"
        self.promises_dir = self.data_dir / "promises"
        self.reports_dir = self.data_dir / "reports"
        self.chapters_dir = self.data_dir / "chapters"

def test_context_retriever_cold_start_fallback(tmp_path):
    # Test fallback to empty dicts when no files exist
    config = DummyConfig(tmp_path)
    retriever = ContextRetriever(config)

    context, active_chars = retriever.retrieve_context("Alice was in the drawing room.")

    assert context is None
    assert active_chars == []


def test_context_retriever_uses_live_state_directly_no_disk(tmp_path):
    """The primary path: a live NarrativeState passed in directly, with NO
    narrative_state.json on disk at all. This must work on its own — it should not
    silently depend on (or require) the disk-read fallback to produce real context."""
    from src.models.state import NarrativeState, StateEntry, StateSnapshot, NarrativeElementType

    config = DummyConfig(tmp_path)
    retriever = ContextRetriever(config)

    state = NarrativeState()
    name_entry = StateEntry(key="canonical_name", element_type=NarrativeElementType.CHARACTER)
    name_entry.update(StateSnapshot(value="Talia", chapter=1))
    state.characters["talia"] = {"canonical_name": name_entry}

    assert not (tmp_path / "narrative_state.json").exists()

    context, active_chars = retriever.retrieve_context("Talia walked in.", current_state=state)

    assert "talia" in active_chars
    assert context is not None
    assert "<Character id=\"talia\">" in context
    # Still no file was ever written or read for this to work.
    assert not (tmp_path / "narrative_state.json").exists()

def test_context_retriever_boundary_safe_regex(tmp_path):
    config = DummyConfig(tmp_path)
    retriever = ContextRetriever(config)

    # Single source of truth: narrative_state.json (the canonical file), not the
    # scattered legacy files this class used to also try reading.
    char_mem = {
        "al": {
            "canonical_name": {"current": {"value": "Al"}},
            "aliases": {"current": {"value": ["Al"]}}
        },
        "alice": {
            "canonical_name": {"current": {"value": "Alice"}},
            "aliases": {"current": {"value": ["Ally"]}}
        }
    }
    with open(tmp_path / "narrative_state.json", "w", encoding="utf-8") as f:
        json.dump({"characters": char_mem}, f)

    # Scenario 1: "Alice went to Millhaven." - Should match "alice" but NOT "al"
    _, active_chars = retriever.retrieve_context("Alice went to Millhaven.")
    assert "alice" in active_chars
    assert "al" not in active_chars

    # Scenario 2: "He walked calmly with Al." - Should match "al" (Al)
    _, active_chars = retriever.retrieve_context("He walked calmly with Al.")
    assert "al" in active_chars

    # Scenario 3: "Alfred went home." - Should match neither "al" nor "alice"
    _, active_chars = retriever.retrieve_context("Alfred went home.")
    assert "al" not in active_chars
    assert "alice" not in active_chars

def test_context_retriever_four_tiers(tmp_path):
    config = DummyConfig(tmp_path)
    retriever = ContextRetriever(config)

    # All four tiers live under one canonical narrative_state.json now, not four
    # separate legacy files.
    char_mem = {
        "talia": {
            "canonical_name": {"current": {"value": "Talia"}},
            "location": {"current": {"value": "drawing_room"}},
            "inventory": {"current": {"value": ["poisoned_milk"]}},
            "goals": {"current": {"value": ["Expose the murderer"]}},
            "fears": {"current": {"value": ["Being caught"]}}
        },
        "mr_whitmore": {
            "canonical_name": {"current": {"value": "Mr. Whitmore"}},
            "location": {"current": {"value": "drawing_room"}}
        }
    }
    relationships = {
        "talia::mr_whitmore": {
            "relationship_label": {"current": {"value": "ENMITY"}},
            "reasoning": {"current": {"value": "Talia is blackmailing Mr. Whitmore"}}
        }
    }
    promises = {
        "vow_1": {
            "speaker_id": {"current": {"value": "talia"}},
            "listener_id": {"current": {"value": "mr_whitmore"}},
            "promise_text": {"current": {"value": "I will make you pay."}},
            "status": {"current": {"value": "OPEN"}},
            "chapter_made": {"current": {"value": 1}}
        }
    }
    world = {
        "drawing_room": {
            "type": {"current": {"value": "location"}},
            "canonical_name": {"current": {"value": "The Drawing Room"}}
        },
        "poisoned_milk": {
            "type": {"current": {"value": "object"}},
            "location": {"current": {"value": "drawing_room"}},
            "status": {"current": {"value": "poisoned"}},
            "description": {"current": {"value": "Found on the mahogany table."}}
        }
    }
    with open(tmp_path / "narrative_state.json", "w", encoding="utf-8") as f:
        json.dump({
            "characters": char_mem,
            "relationships": relationships,
            "promises": promises,
            "world": world,
        }, f)

    # Run retriever for scene mentioning Talia, Mr. Whitmore, and Drawing Room
    context, active_chars = retriever.retrieve_context("Talia met Mr. Whitmore inside the Drawing Room.")
    assert "talia" in active_chars
    assert "mr_whitmore" in active_chars

    # Assert Tiers A, B, C, D are present in XML
    assert "<Character id=\"talia\">" in context
    assert "<Relationship party_a=\"mr_whitmore\" party_b=\"talia\">" in context or "<Relationship party_a=\"talia\" party_b=\"mr_whitmore\">" in context
    assert "Talia is blackmailing Mr. Whitmore" in context
    assert "<Promise speaker=\"talia\" listener=\"mr_whitmore\" status=\"OPEN\"" in context
    assert "<Clue id=\"poisoned_milk\">" in context
    assert "<Location>drawing_room</Location>" in context

def test_context_retriever_budget_truncation(tmp_path):
    config = DummyConfig(tmp_path)
    retriever = ContextRetriever(config)

    # Setup character profile (Tier A) plus a giant relationship profile (Tier B) that
    # exceeds 6000 chars, both under the one canonical narrative_state.json.
    char_mem = {
        "talia": {
            "canonical_name": {"current": {"value": "Talia"}}
        },
        "mr_whitmore": {
            "canonical_name": {"current": {"value": "Mr. Whitmore"}}
        }
    }
    giant_text = "A" * 7000
    relationships = {
        "mr_whitmore::talia": {
            "relationship_label": {"current": {"value": "ENMITY"}},
            "reasoning": {"current": {"value": giant_text}}
        }
    }
    with open(tmp_path / "narrative_state.json", "w", encoding="utf-8") as f:
        json.dump({"characters": char_mem, "relationships": relationships}, f)

    context, active_chars = retriever.retrieve_context("Talia spoke to Mr. Whitmore.")
    assert "talia" in active_chars
    assert "mr_whitmore" in active_chars

    # The total length must be constrained under 6000 chars (plus small tag buffer)
    assert len(context) < 6200
    # Tier A must still be present
    assert "<Character id=\"talia\">" in context
    # Relationship with giant text must have been truncated/omitted
    assert giant_text not in context
