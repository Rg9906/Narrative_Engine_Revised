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

def test_context_retriever_boundary_safe_regex(tmp_path):
    config = DummyConfig(tmp_path)
    retriever = ContextRetriever(config)

    # Setup character_memory.json with "al" and "alice"
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
    with open(tmp_path / "character_memory.json", "w", encoding="utf-8") as f:
        json.dump(char_mem, f)

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

    # 1. Characters Profile
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
    with open(tmp_path / "character_memory.json", "w", encoding="utf-8") as f:
        json.dump(char_mem, f)

    # 2. Relationships Matrix
    relationships = {
        "talia::mr_whitmore": {
            "relationship_label": {"current": {"value": "ENMITY"}},
            "reasoning": {"current": {"value": "Talia is blackmailing Mr. Whitmore"}}
        }
    }
    with open(tmp_path / "relationship_memory.json", "w", encoding="utf-8") as f:
        json.dump(relationships, f)

    # 3. Unresolved Promises
    promises = {
        "vow_1": {
            "speaker_id": {"current": {"value": "talia"}},
            "listener_id": {"current": {"value": "mr_whitmore"}},
            "promise_text": {"current": {"value": "I will make you pay."}},
            "status": {"current": {"value": "OPEN"}},
            "chapter_made": {"current": {"value": 1}}
        }
    }
    with open(tmp_path / "vows.json", "w", encoding="utf-8") as f:
        json.dump(promises, f)

    # 4. World Locations and Objects (Physical Clues)
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
    with open(tmp_path / "world_memory.json", "w", encoding="utf-8") as f:
        json.dump(world, f)

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

    # Setup character profile (Tier A)
    char_mem = {
        "talia": {
            "canonical_name": {"current": {"value": "Talia"}}
        },
        "mr_whitmore": {
            "canonical_name": {"current": {"value": "Mr. Whitmore"}}
        }
    }
    with open(tmp_path / "character_memory.json", "w", encoding="utf-8") as f:
        json.dump(char_mem, f)

    # Setup a giant relationship profile (Tier B) and giant promise (Tier C) that exceeds 6000 chars
    giant_text = "A" * 7000
    relationships = {
        "mr_whitmore::talia": {
            "relationship_label": {"current": {"value": "ENMITY"}},
            "reasoning": {"current": {"value": giant_text}}
        }
    }
    with open(tmp_path / "relationship_memory.json", "w", encoding="utf-8") as f:
        json.dump(relationships, f)

    context, active_chars = retriever.retrieve_context("Talia spoke to Mr. Whitmore.")
    assert "talia" in active_chars
    assert "mr_whitmore" in active_chars

    # The total length must be constrained under 6000 chars (plus small tag buffer)
    assert len(context) < 6200
    # Tier A must still be present
    assert "<Character id=\"talia\">" in context
    # Relationship with giant text must have been truncated/omitted
    assert giant_text not in context
