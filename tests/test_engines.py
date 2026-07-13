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

    def test_pacing_inspector_extreme_word_count(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 1
        state.total_chapters_processed = 1

        from src.models.state import StateEntry, StateSnapshot
        wc_entry = StateEntry(key="word_count")
        wc_entry.update(StateSnapshot(value=200, chapter=1)) # Very short chapter
        state.style["global_style"] = {"word_count": wc_entry}

        report = engine.review(state)
        findings = report["findings"]

        assert any(f["category"] == "pacing" and "very short chapter" in f["title"].lower() for f in findings)

    def test_voice_inspector_sudden_style_shift(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 2
        state.total_chapters_processed = 2

        from src.models.state import StateEntry, StateSnapshot
        avg_len_entry = StateEntry(key="avg_sentence_length")
        avg_len_entry.update(StateSnapshot(value=15.0, chapter=1)) # Chapter 1 avg sentence length
        avg_len_entry.update(StateSnapshot(value=25.0, chapter=2)) # Chapter 2 avg sentence length (diff is 10.0 > 8.0)
        state.style["global_style"] = {"avg_sentence_length": avg_len_entry}

        report = engine.review(state)
        findings = report["findings"]

        assert any(f["category"] == "voice" and "sudden prose style shift" in f["title"].lower() for f in findings)

    def test_scene_engine_advanced_boundaries(self):
        engine = SceneEngine()
        # Test text with visual break and transition phrase
        text = """Paragraph one of the first scene.

* * *

Paragraph two starting a new scene because of visual break.

The next day, Arthur woke up early in his quarters. This paragraph starts with a transition phrase."""
        
        scenes = engine.detect_scenes(text, chapter_num=1)
        # Should detect 3 scenes:
        # Scene 1: Paragraph one
        # Scene 2: Paragraph two
        # Scene 3: The next day paragraph
        assert len(scenes) == 3
        assert "Setting Transition" in scenes[2]["title"]

    def test_editorial_engine_parse_json_findings(self):
        engine = EditorialEngine()
        raw_output = """```json
[
  {
    "severity": "warning",
    "category": "consistency",
    "title": "Unresolved Mystery",
    "description": "The chalice is still missing.",
    "confidence": 0.9
  }
]
```"""
        findings = engine._parse_json_findings(raw_output, chapter_num=5)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 5
        assert findings[0]["title"] == "Unresolved Mystery"

    def test_editorial_engine_parse_json_findings_robust(self):
        engine = EditorialEngine()
        raw_output_conversational = """Here is the critique you requested:
[
  {
    "severity": "warning",
    "category": "consistency",
    "title": "Unresolved Mystery",
    "description": "The chalice is still missing.",
    "confidence": 0.9
  }
]
Hope that helps with your developmental editing process!"""
        findings = engine._parse_json_findings(raw_output_conversational, chapter_num=5)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 5
        assert findings[0]["title"] == "Unresolved Mystery"

        # Test single object returned instead of list
        raw_output_single_object = """{
    "severity": "suggestion",
    "category": "pacing",
    "title": "Slow Pacing",
    "description": "Scene 2 drags on.",
    "confidence": 0.8
}"""
        findings = engine._parse_json_findings(raw_output_single_object, chapter_num=2)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 2
        assert findings[0]["severity"] == "suggestion"

    def test_editorial_engine_llm_context_goals(self, monkeypatch):
        # Setup a state with a character having a goal
        state = NarrativeState()
        state.last_processed_chapter = 1
        state.total_chapters_processed = 1
        
        from src.models.state import StateEntry, StateSnapshot, StateDelta
        name_entry = StateEntry(key="canonical_name")
        name_entry.update(StateSnapshot(value="Arthur", chapter=1))
        
        goals_entry = StateEntry(key="goals")
        goals_entry.update(StateSnapshot(value=["find the grail"], chapter=1))
        
        state.characters["arthur"] = {
            "canonical_name": name_entry,
            "goals": goals_entry
        }
        
        engine = EditorialEngine()
        # Mock LLMProvider to be available
        monkeypatch.setattr(engine._llm, "_provider", "mock_llm")
        monkeypatch.setattr(engine._llm, "_model", "mock-model")
        
        captured_messages = []
        def mock_chat(messages):
            captured_messages.extend(messages)
            return "[]" # Return empty findings
            
        monkeypatch.setattr(engine._llm, "chat", mock_chat)
        
        delta = StateDelta(chapter_number=1)
        engine._run_llm_critique(state, delta)
        
        assert len(captured_messages) == 2
        user_prompt = captured_messages[1]["content"]
        assert "Goals: ['find the grail']" in user_prompt



class TestLLMProvider:
    """Tests for the centralized LLMProvider backend detection."""

    def test_provider_detects_gemini(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-123")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_API_URL", raising=False)

        from src.utils.llm_provider import LLMProvider
        provider = LLMProvider()
        assert provider.provider_name == "gemini"
        assert provider.is_available is True
        assert provider.model == "gemini-2.0-flash"

    def test_provider_detects_groq(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-456")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_API_URL", raising=False)

        from src.utils.llm_provider import LLMProvider
        provider = LLMProvider()
        assert provider.provider_name == "groq"
        assert provider.is_available is True
        assert provider.model == "llama-3.3-70b-versatile"

    def test_provider_priority_gemini_over_groq(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-123")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-456")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_API_URL", raising=False)

        from src.utils.llm_provider import LLMProvider
        provider = LLMProvider()
        assert provider.provider_name == "gemini"

    def test_provider_falls_back_to_none(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_API_URL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        from src.utils.llm_provider import LLMProvider
        # Patch _check_ollama_alive to always return False (no local server)
        monkeypatch.setattr(LLMProvider, "_check_ollama_alive", staticmethod(lambda url: False))
        provider = LLMProvider()
        assert provider.provider_name == "none"
        assert provider.is_available is False

    def test_provider_chat_raises_when_unavailable(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_API_URL", raising=False)

        from src.utils.llm_provider import LLMProvider
        monkeypatch.setattr(LLMProvider, "_check_ollama_alive", staticmethod(lambda url: False))
        provider = LLMProvider()
        with pytest.raises(RuntimeError, match="No LLM provider available"):
            provider.chat([{"role": "user", "content": "test"}])


def test_narrative_state_engine_reconciliation_and_decay():
    from src.engines.narrative_state import NarrativeStateEngine
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType, StateChange, StateChangeType, StateDelta
    
    # 1. Test Trait Decay
    engine = NarrativeStateEngine(None)
    state = NarrativeState()
    
    # Setup character with personality trait
    char_entry = StateEntry(key="personality_traits", element_type=NarrativeElementType.CHARACTER)
    char_entry.update(StateSnapshot(value=["brave"], chapter=1, confidence=0.8))
    state.characters["arthur"] = {"personality_traits": char_entry}
    
    delta = StateDelta(chapter_number=2)
    # Empty changes (Arthur's traits not updated in ch 2)
    engine.apply_confidence_decay(state, delta)
    
    decayed_conf = state.characters["arthur"]["personality_traits"].current.confidence
    assert decayed_conf == 0.78  # 0.8 - 0.02

    # 2. Test Contradiction Reconciliation
    hair_entry = StateEntry(key="physical_hair_color", element_type=NarrativeElementType.CHARACTER)
    hair_entry.update(StateSnapshot(value="blonde", chapter=1, confidence=0.9))
    state.characters["arthur"]["physical_hair_color"] = hair_entry
    
    # New conflicting change with lower confidence (0.5 < 0.9)
    change = StateChange(
        change_type=StateChangeType.EVOLUTION,
        target_type=NarrativeElementType.CHARACTER,
        target_id="arthur",
        field_key="physical_hair_color",
        old_value="blonde",
        new_value="black",
        confidence=0.5
    )
    delta.changes = [change]
    
    reconciled = engine.reconcile_state_changes(state, delta)
    
    # Conflicting change is turned to CONTRADICTION
    assert reconciled[0].change_type == StateChangeType.CONTRADICTION
    # Value is reverted to old_value in state entries
    assert state.characters["arthur"]["physical_hair_color"].current.value == "blonde"
    # Logged conflict mystery
    assert len(state.mysteries) > 0
    conflict_key = list(state.mysteries.keys())[0]
    assert "conflict_arthur_physical_hair_color" in conflict_key


def test_char_inspector_inventory_teleportation():
    from src.review.char_inspector import CharacterInspector
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType
    
    state = NarrativeState()
    state.last_processed_chapter = 2
    
    # Setup character with item in inventory but at different location
    char_entry = {
        "inventory": StateEntry(key="inventory", element_type=NarrativeElementType.CHARACTER),
        "location": StateEntry(key="location", element_type=NarrativeElementType.CHARACTER)
    }
    char_entry["inventory"].update(StateSnapshot(value=["sword"], chapter=2))
    char_entry["location"].update(StateSnapshot(value="castle", chapter=2))
    state.characters["arthur"] = char_entry
    
    # Setup item in world left at cave
    item_entry = {
        "location": StateEntry(key="location", element_type=NarrativeElementType.OBJECT),
        "owner": StateEntry(key="owner", element_type=NarrativeElementType.OBJECT)
    }
    item_entry["location"].update(StateSnapshot(value="cave", chapter=1))
    item_entry["owner"].update(StateSnapshot(value=None, chapter=1)) # left there
    state.world["sword"] = item_entry
    
    inspector = CharacterInspector()
    findings = inspector.inspect(state, None)
    
    assert len(findings) > 0
    assert any("teleportation" in f.title.lower() for f in findings)


def test_relationship_inspector_emotional_inversion():
    from src.review.relationship_inspector import RelationshipInspector
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType
    
    state = NarrativeState()
    state.last_processed_chapter = 2
    
    rel_entry = {
        "relationship_label": StateEntry(key="relationship_label", element_type=NarrativeElementType.CHARACTER)
    }
    # Direct jump: ENMITY -> ROMANTIC
    rel_entry["relationship_label"].update(StateSnapshot(value="ENMITY", chapter=1))
    rel_entry["relationship_label"].update(StateSnapshot(value="ROMANTIC", chapter=2))
    state.relationships["arthur::guinevere"] = rel_entry
    
    inspector = RelationshipInspector()
    findings = inspector.inspect(state, None)
    
    assert len(findings) > 0
    assert any("emotional inversion" in f.title.lower() for f in findings)

