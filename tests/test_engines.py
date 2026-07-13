"""Unit tests for Narrative Intelligence Engine reasoning engines."""

import pytest
from pathlib import Path
from src.models.state import ChapterData, ExtractedEntity, ExtractedDialogue, ExtractedRelation, NarrativeState, StateDelta
from src.engines.scene_engine import SceneEngine
from src.engines.narrative_graph import NarrativeGraph
from src.engines.editorial_engine import EditorialEngine


@pytest.fixture
def sample_chapter_data():
    cd = ChapterData(
        chapter_number=1,
        source_name="test_novel.txt",
        chapter_title="Chapter 1: The Gathering Storm",
        raw_text="""Chapter 1: The Gathering Storm

The castle was quiet. Arthur stood by the window, watching the rain pour. He was worried about the kingdom.

"We must prepare," said Merlin, walking into the room. Arthur turned to him. "Preparing won't be enough."

Merlin sighed. "The dark army is coming, Arthur."
""",
        paragraphs=[
            "Chapter 1: The Gathering Storm",
            "The castle was quiet. Arthur stood by the window, watching the rain pour. He was worried about the kingdom.",
            '"We must prepare," said Merlin, walking into the room. Arthur turned to him. "Preparing won\'t be enough."',
            'Merlin sighed. "The dark army is coming, Arthur."'
        ],
        sentences=[
            "Chapter 1: The Gathering Storm",
            "The castle was quiet.",
            "Arthur stood by the window, watching the rain pour.",
            "He was worried about the kingdom.",
            '"We must prepare," said Merlin, walking into the room.',
            'Arthur turned to him.',
            '"Preparing won\'t be enough."',
            'Merlin sighed.',
            '"The dark army is coming, Arthur."'
        ]
    )
    # Add extracted entities and SVO relations
    cd.entities = [
        ExtractedEntity(text="Arthur", label="person", confidence=1.0),
        ExtractedEntity(text="Merlin", label="person", confidence=1.0),
        ExtractedEntity(text="castle", label="location", confidence=1.0)
    ]
    cd.relations = [
        ExtractedRelation(subject="Arthur", predicate="stood", object="window", confidence=1.0),
        ExtractedRelation(subject="Merlin", predicate="sighs", object="Arthur", confidence=1.0)
    ]
    cd.dialogues = [
        ExtractedDialogue(speaker="Merlin", text="We must prepare", confidence=0.8, attribution_method="speech_tag_after"),
        ExtractedDialogue(speaker="Arthur", text="Preparing won't be enough", confidence=0.8, attribution_method="unattributed_quote"),
        ExtractedDialogue(speaker="Merlin", text="The dark army is coming, Arthur", confidence=0.8, attribution_method="speech_tag_before")
    ]
    return cd


class TestSceneEngine:
    def test_scene_boundary_and_pov_detection(self, sample_chapter_data):
        engine = SceneEngine()
        scenes = engine.detect_scenes(sample_chapter_data.raw_text, 1)

        # Assert scene splitting happened
        assert len(scenes) > 0
        
        # Analyze richness
        character_names = {"Arthur", "Merlin"}
        analyzed_scenes = engine.analyze_all_scenes(scenes, sample_chapter_data, character_names)
        
        assert len(analyzed_scenes) > 0
        first_scene = analyzed_scenes[0]
        assert "pov" in first_scene
        assert first_scene["pov"] in character_names
        assert "Arthur" in first_scene["characters_present"] or "Merlin" in first_scene["characters_present"]


class TestNarrativeGraph:
    def test_graph_building(self):
        state = NarrativeState()
        # Mock some entries
        state.total_chapters_processed = 1
        state.last_processed_chapter = 1
        
        # Add character entry
        from src.models.state import StateEntry, StateSnapshot
        char_entry = StateEntry(key="canonical_name")
        char_entry.update(StateSnapshot(value="Arthur", chapter=1))
        state.characters["arthur"] = {"canonical_name": char_entry}

        graph_builder = NarrativeGraph(None)
        graph = graph_builder.build(state)

        assert "nodes" in graph
        assert "edges" in graph
        assert any(n["id"] == "char::arthur" for n in graph["nodes"])


class TestEditorialEngine:
    def test_editorial_engine_runs_inspectors(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 1
        state.total_chapters_processed = 1
        
        # Mock character Arthur with 1 mention (should trigger underdeveloped character check)
        from src.models.state import StateEntry, StateSnapshot
        mention_entry = StateEntry(key="mention_count")
        mention_entry.update(StateSnapshot(value=1, chapter=1))
        state.characters["arthur"] = {"mention_count": mention_entry}

        delta = StateDelta(chapter_number=1)
        report = engine.review(state, delta)

        assert "findings" in report
        # Underdeveloped character Arthur should be flagged
        assert len(report["findings"]) > 0
        assert any(f["category"] == "character" and "underdeveloped" in f["title"].lower() for f in report["findings"])

    def test_relationship_inspector_abrupt_shift(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 2
        state.total_chapters_processed = 2

        # Create relationship arthur::merlin transitioning ENMITY -> ROMANTIC
        from src.models.state import StateEntry, StateSnapshot
        rel_label = StateEntry(key="relationship_label")
        rel_label.update(StateSnapshot(value="ENMITY", chapter=1))
        rel_label.update(StateSnapshot(value="ROMANTIC", chapter=2))
        state.relationships["arthur::merlin"] = {"relationship_label": rel_label}

        report = engine.review(state)
        findings = report["findings"]

        assert any(f["category"] == "consistency" and "relationship shift" in f["title"].lower() for f in findings)

    def test_timeline_inspector_post_mortem_and_jumps(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 3
        state.total_chapters_processed = 3

        # Add event out of order (jump)
        state.timeline = [
            {"chapter": 2, "subject": "Arthur", "predicate": "attacks", "object": "beast"},
            {"chapter": 1, "subject": "Merlin", "predicate": "brews", "object": "potion"},
            # Death event in chapter 2
            {"chapter": 2, "subject": "Arthur", "predicate": "dies", "object": "in battle"},
            # Post-mortem action in chapter 3
            {"chapter": 3, "subject": "Arthur", "predicate": "revives", "object": "the crown"},
        ]

        report = engine.review(state)
        findings = report["findings"]

        assert any(f["category"] == "consistency" and "timeline jump" in f["title"].lower() for f in findings)
        assert any(f["category"] == "consistency" and "post-mortem" in f["title"].lower() for f in findings)

    def test_conflict_inspector_neglected_mystery(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 8
        state.total_chapters_processed = 8

        # Create neglected mystery introduced in chapter 1, status unresolved
        from src.models.state import StateEntry, StateSnapshot
        status_entry = StateEntry(key="status")
        status_entry.update(StateSnapshot(value="unresolved", chapter=1))
        
        intro_entry = StateEntry(key="chapter_introduced")
        intro_entry.update(StateSnapshot(value=1, chapter=1))

        text_entry = StateEntry(key="mystery_text")
        text_entry.update(StateSnapshot(value="Who stole the chalice?", chapter=1))

        state.mysteries["mystery_1"] = {
            "status": status_entry,
            "chapter_introduced": intro_entry,
            "mystery_text": text_entry
        }

        report = engine.review(state)
        findings = report["findings"]

        assert any(f["category"] == "conflict" and "neglected mystery" in f["title"].lower() for f in findings)
