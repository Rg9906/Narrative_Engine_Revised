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

        # Regression: node label must be the actual display name ("Arthur"),
        # not the raw entity id ("arthur") -- a prior bug called _entry_value()
        # on the whole fields-dict instead of the canonical_name field, which
        # always fell through to the id.
        arthur_node = next(n for n in graph["nodes"] if n["id"] == "char::arthur")
        assert arthur_node["label"] == "Arthur"

    def test_character_world_and_theme_edges(self):
        """Characters and world/theme elements sharing an active chapter get
        connected; those that never co-occur do not."""
        from src.models.state import StateEntry, StateSnapshot

        state = NarrativeState()
        state.total_chapters_processed = 3

        # Arthur active in chapters 1 and 2; Merlin only in chapter 5.
        arthur_name = StateEntry(key="canonical_name")
        arthur_name.update(StateSnapshot(value="Arthur", chapter=1))
        arthur_name.update(StateSnapshot(value="Arthur", chapter=2))
        state.characters["arthur"] = {"canonical_name": arthur_name}

        merlin_name = StateEntry(key="canonical_name")
        merlin_name.update(StateSnapshot(value="Merlin", chapter=5))
        state.characters["merlin"] = {"canonical_name": merlin_name}

        # Castle active in chapter 1 (overlaps Arthur) — expect an edge.
        castle_type = StateEntry(key="type")
        castle_type.update(StateSnapshot(value="location", chapter=1))
        state.world["castle"] = {"type": castle_type}

        # Cave active only in chapter 9 — no overlap with anyone.
        cave_type = StateEntry(key="type")
        cave_type.update(StateSnapshot(value="location", chapter=9))
        state.world["cave"] = {"type": cave_type}

        # Theme "power" present in chapters [2, 3] — overlaps Arthur (ch. 2),
        # not Merlin (ch. 5 only).
        power_chapters = StateEntry(key="chapters_present")
        power_chapters.update(StateSnapshot(value=[2, 3], chapter=2))
        state.themes["theme_power"] = {"chapters_present": power_chapters}

        graph_builder = NarrativeGraph(None)
        graph = graph_builder.build(state)
        edges_by_id = {e["id"]: e for e in graph["edges"]}

        assert "char_world::arthur::castle" in edges_by_id
        assert edges_by_id["char_world::arthur::castle"]["type"] == "character_world"
        assert "char_world::merlin::castle" not in edges_by_id
        assert "char_world::arthur::cave" not in edges_by_id

        assert "char_theme::arthur::theme_power" in edges_by_id
        assert edges_by_id["char_theme::arthur::theme_power"]["type"] == "character_theme"
        assert "char_theme::merlin::theme_power" not in edges_by_id

        # Label fallback: no canonical_name/theme_name field present on "castle"
        # or "theme_power" here, so labels fall back to a humanized id rather
        # than the empty/None _entry_value() used to silently produce.
        nodes_by_id = {n["id"]: n for n in graph["nodes"]}
        assert nodes_by_id["world::castle"]["label"] == "Castle"
        assert nodes_by_id["theme::theme_power"]["label"] == "Theme Power"


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

    def test_pacing_inspector_zero_indexed_chapters_no_false_gap(self):
        """Regression test: PacingInspector._check_chapter_distribution assumed
        1-indexed chapters, so a genuine gap-free 0-indexed run (chapters
        0, 1, 2, 3 -- last_processed_chapter=3, total_chapters_processed=4)
        was incorrectly flagged as a gap ("expected 3 but processed 4").
        Confirmed present in this project's own real
        data/reports/editorial_report_ch3.json before this fix."""
        from src.review.pacing_inspector import PacingInspector

        state = NarrativeState()
        state.last_processed_chapter = 3
        state.total_chapters_processed = 4

        inspector = PacingInspector()
        findings = inspector.inspect(state, None)

        assert not any("chapter processing gap" in f.title.lower() for f in findings)

    def test_pacing_inspector_real_gap_still_detected(self):
        """A genuine gap (chapters 0-2 processed, but last_processed_chapter
        jumped to 5) should still be flagged under either indexing
        convention."""
        from src.review.pacing_inspector import PacingInspector

        state = NarrativeState()
        state.last_processed_chapter = 5
        state.total_chapters_processed = 3

        inspector = PacingInspector()
        findings = inspector.inspect(state, None)

        assert any("chapter processing gap" in f.title.lower() for f in findings)

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
        findings, key_events = engine._parse_json_findings(raw_output, chapter_num=5)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 5
        assert findings[0]["title"] == "Unresolved Mystery"
        assert key_events == []

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
        findings, key_events = engine._parse_json_findings(raw_output_conversational, chapter_num=5)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 5
        assert findings[0]["title"] == "Unresolved Mystery"
        assert key_events == []

        # Test single finding object returned instead of a findings/key_events wrapper
        raw_output_single_object = """{
    "severity": "suggestion",
    "category": "pacing",
    "title": "Slow Pacing",
    "description": "Scene 2 drags on.",
    "confidence": 0.8
}"""
        findings, key_events = engine._parse_json_findings(raw_output_single_object, chapter_num=2)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 2
        assert findings[0]["severity"] == "suggestion"
        assert key_events == []

        # Test the new expected shape: an object with both 'findings' and 'key_events'
        raw_output_wrapped = """{
    "findings": [
        {"severity": "note", "category": "theme", "title": "Motif", "description": "Recurring rain imagery.", "confidence": 0.7}
    ],
    "key_events": ["Arthur found the grail.", "The castle gates were sealed."]
}"""
        findings, key_events = engine._parse_json_findings(raw_output_wrapped, chapter_num=3)
        assert len(findings) == 1
        assert findings[0]["chapter"] == 3
        assert key_events == ["Arthur found the grail.", "The castle gates were sealed."]

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
        # raw_text must actually mention "Arthur" — the critique now goes through
        # ContextRetriever (see Phase 8), which only includes characters textually
        # active in the chapter being reviewed, not the whole character roster.
        engine._run_llm_critique(state, delta, raw_text="Arthur searched the castle for the grail.")

        assert len(captured_messages) == 2
        user_prompt = captured_messages[1]["content"]
        assert "<Goals>find the grail</Goals>" in user_prompt



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

    # 2. Test cross-character inventory conflict detection — the one responsibility
    # reconcile_state_changes still has (see its docstring: per-field contradiction
    # detection moved to ValidationEngine, called pre-write from StateEngine, since this
    # method used to read state AFTER the write already landed and could never actually
    # catch a same-chapter contradiction).
    state.characters["arthur"]["inventory"] = StateEntry(key="inventory", element_type=NarrativeElementType.CHARACTER)
    state.characters["arthur"]["inventory"].update(StateSnapshot(value=["sword"], chapter=2, confidence=0.9))
    state.characters["merlin"] = {
        "inventory": StateEntry(key="inventory", element_type=NarrativeElementType.CHARACTER)
    }
    state.characters["merlin"]["inventory"].update(StateSnapshot(value=["sword", "staff"], chapter=2, confidence=0.9))

    inv_change = StateChange(
        change_type=StateChangeType.EVOLUTION,
        target_type=NarrativeElementType.CHARACTER,
        target_id="arthur",
        field_key="inventory",
        old_value=[],
        new_value=["sword"],
        confidence=0.9,
    )
    delta.changes = [inv_change]

    reconciled = engine.reconcile_state_changes(state, delta)

    # The change itself passes through unmodified (this layer flags, it doesn't revert)
    assert reconciled[0].change_type == StateChangeType.EVOLUTION
    # But a dual-ownership conflict mystery was logged for the shared "sword"
    assert any("conflict_inv_sword" in k for k in state.mysteries.keys())


def test_narrative_state_engine_reconciliation_catches_first_time_dual_ownership():
    """Regression test: reconcile_state_changes previously only cross-checked
    inventory dual-ownership for EVOLUTION/CONTRADICTION changes, so two
    characters each given the same item for the FIRST time in one chapter
    (both changes are type INTRODUCTION) were never caught. Caught by a
    self-review pass."""
    from src.engines.narrative_state import NarrativeStateEngine
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType, StateChange, StateChangeType, StateDelta

    engine = NarrativeStateEngine(None)
    state = NarrativeState()

    state.characters["arthur"] = {"inventory": StateEntry(key="inventory", element_type=NarrativeElementType.CHARACTER)}
    state.characters["arthur"]["inventory"].update(StateSnapshot(value=["lantern"], chapter=1, confidence=0.9))
    state.characters["merlin"] = {"inventory": StateEntry(key="inventory", element_type=NarrativeElementType.CHARACTER)}
    state.characters["merlin"]["inventory"].update(StateSnapshot(value=["lantern"], chapter=1, confidence=0.9))

    # Both characters' FIRST-ever inventory entry -> both changes are INTRODUCTION.
    intro_change = StateChange(
        change_type=StateChangeType.INTRODUCTION,
        target_type=NarrativeElementType.CHARACTER,
        target_id="arthur",
        field_key="inventory",
        old_value=None,
        new_value=["lantern"],
        confidence=0.9,
    )
    delta = StateDelta(chapter_number=1, changes=[intro_change])

    engine.reconcile_state_changes(state, delta)

    assert any("conflict_inv_lantern" in k for k in state.mysteries.keys())


def test_validation_engine_field_contradiction():
    """Field-level contradiction detection now lives in ValidationEngine, applied BEFORE
    a value is written (see src/engines/validation_engine.py and StateEngine's character/
    world update loops) rather than after, so it can actually suppress a bad write."""
    from src.engines.validation_engine import ValidationEngine

    validator = ValidationEngine(None)

    # Lower-confidence contradiction on a stability-expected field: flagged AND suppressed.
    result = validator.check_field_contradiction(
        field_key="physical_hair_color", old_value="blonde", old_confidence=0.9,
        new_value="black", new_confidence=0.5,
    )
    assert result.is_contradiction is True
    assert result.should_apply is False

    # Equal-or-higher confidence contradiction: flagged, but still applied.
    result2 = validator.check_field_contradiction(
        field_key="physical_hair_color", old_value="blonde", old_confidence=0.5,
        new_value="black", new_confidence=0.9,
    )
    assert result2.is_contradiction is True
    assert result2.should_apply is True

    # Fields expected to evolve every chapter (goals, location, ...) are never flagged.
    result3 = validator.check_field_contradiction(
        field_key="goals", old_value=["escape"], old_confidence=0.9,
        new_value=["confront the king"], new_confidence=0.5,
    )
    assert result3.is_contradiction is False
    assert result3.should_apply is True


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


def test_arc_inspector_unresolved_arc_near_story_end():
    """Regression test: ArcInspector._check_unresolved_arcs was fully
    implemented but never called from inspect(), so this finding silently
    never fired. Caught by a self-review pass."""
    from src.review.arc_inspector import ArcInspector
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType

    state = NarrativeState()
    state.last_processed_chapter = 16  # past the chapter < 15 gate

    arc_entry = StateEntry(key="arc_stage", element_type=NarrativeElementType.CHARACTER)
    arc_entry.update(StateSnapshot(value="rising_action", chapter=16))
    mention_entry = StateEntry(key="mention_count", element_type=NarrativeElementType.CHARACTER)
    mention_entry.update(StateSnapshot(value=12, chapter=16))
    state.characters["arthur"] = {"arc_stage": arc_entry, "mention_count": mention_entry}

    inspector = ArcInspector()
    findings = inspector.inspect(state, None)

    assert any("unresolved character arc" in f.title.lower() for f in findings)


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


def test_split_manuscript_utility(tmp_path):
    from scripts.split_manuscript import split_manuscript
    
    manuscript_content = (
        "Chapter 1\nThis is the first chapter content.\n"
        "### CHAPTER II\nThis is the second chapter with markdown.\n"
        "Chapter Three\nAnd the third chapter here.\n"
    )
    manuscript_file = tmp_path / "monolithic.txt"
    manuscript_file.write_text(manuscript_content, encoding="utf-8")
    
    output_dir = tmp_path / "chapters"
    split_manuscript(manuscript_file, output_dir)
    
    # Check output files
    ch1_file = output_dir / "chapter_01.txt"
    ch2_file = output_dir / "chapter_02.txt"
    ch3_file = output_dir / "chapter_03.txt"
    
    assert ch1_file.exists()
    assert ch2_file.exists()
    assert ch3_file.exists()
    
    assert "Chapter 1" in ch1_file.read_text(encoding="utf-8")
    assert "CHAPTER II" in ch2_file.read_text(encoding="utf-8")
    assert "Chapter Three" in ch3_file.read_text(encoding="utf-8")


def test_main_cli_chapter_parsing(tmp_path, monkeypatch):
    import src.main
    from src.models.state import NarrativeState
    
    # Mock load_narrative_state to return empty NarrativeState
    monkeypatch.setattr(src.main, "load_narrative_state", lambda path: NarrativeState())
    # Mock save_narrative_state to do nothing
    monkeypatch.setattr(src.main, "save_narrative_state", lambda state, path: None)
    
    # Mock Pipeline and NarrativeStateEngine
    class MockPipeline:
        def __init__(self, config):
            pass
        def process_chapter(self, path, chapter_num, is_file, current_state=None):
            class MockChapterData:
                raw_text = "Arthur was a king."
                chapter_number = chapter_num
            return MockChapterData()
            
    class MockStateEngine:
        def __init__(self, config):
            pass
        def process_chapter(self, data, state):
            from src.models.state import StateDelta
            return StateDelta(chapter_number=1)
            
    monkeypatch.setattr(src.main, "Pipeline", MockPipeline)
    monkeypatch.setattr(src.main, "NarrativeStateEngine", MockStateEngine)
    
    # Verify that file named "chapter_05.txt" resolves chapter number to 5
    chapter_file = tmp_path / "chapter_05.txt"
    chapter_file.write_text("Arthur was a king.", encoding="utf-8")
    
    # Run process_chapter
    # Note: we need to mock EditorialEngine and NarrativeGraph too
    class MockEditorial:
        def __init__(self, config):
            pass
        def review(self, state, delta, raw_text):
            assert raw_text == "Arthur was a king."
            return {"findings": []}
            
    class MockGraph:
        def __init__(self, config):
            pass
        def save(self, state, path):
            return "graph_path"
            
    monkeypatch.setattr(src.main, "EditorialEngine", MockEditorial)
    monkeypatch.setattr(src.main, "NarrativeGraph", MockGraph)

    src.main.process_chapter(str(chapter_file))


def test_process_chapter_records_previous_chapter_excerpt(tmp_path, monkeypatch):
    """Contextual lookback: after processing a chapter, the state should carry
    that chapter's raw-text tail forward for the NEXT chapter's context (not
    the current one) -- see NarrativeState.previous_chapter_excerpt."""
    import src.main
    from src.models.state import NarrativeState, StateDelta

    captured_state = {}

    def fake_load(path):
        return NarrativeState()

    def fake_save(state, path):
        # Capture the state as it stood right before persistence, so we can
        # assert on previous_chapter_excerpt without needing a real state file.
        captured_state["state"] = state

    monkeypatch.setattr(src.main, "load_narrative_state", fake_load)
    monkeypatch.setattr(src.main, "save_narrative_state", fake_save)
    monkeypatch.setattr(src.main, "save_modular_state", lambda state, config: None)

    long_text = "Arthur was a king. " * 200  # well over PREVIOUS_CHAPTER_EXCERPT_CHARS

    class MockPipeline:
        def __init__(self, config):
            pass
        def process_chapter(self, path, chapter_num, is_file, current_state=None):
            class MockChapterData:
                raw_text = long_text
                chapter_number = chapter_num
            return MockChapterData()

    class MockStateEngine:
        def __init__(self, config):
            pass
        def process_chapter(self, data, state):
            return StateDelta(chapter_number=data.chapter_number)

    class MockEditorial:
        def __init__(self, config):
            pass
        def review(self, state, delta, raw_text):
            return {"findings": []}

    class MockGraph:
        def __init__(self, config):
            pass
        def save(self, state, path):
            return "graph_path"

    monkeypatch.setattr(src.main, "Pipeline", MockPipeline)
    monkeypatch.setattr(src.main, "NarrativeStateEngine", MockStateEngine)
    monkeypatch.setattr(src.main, "EditorialEngine", MockEditorial)
    monkeypatch.setattr(src.main, "NarrativeGraph", MockGraph)

    chapter_file = tmp_path / "chapter_07.txt"
    chapter_file.write_text(long_text, encoding="utf-8")

    src.main.process_chapter(str(chapter_file))

    state = captured_state["state"]
    assert state.previous_chapter_number == 7
    assert state.previous_chapter_excerpt == long_text[-src.main.PREVIOUS_CHAPTER_EXCERPT_CHARS:].strip()
    assert len(state.previous_chapter_excerpt) <= src.main.PREVIOUS_CHAPTER_EXCERPT_CHARS


def test_optimized_llm_prompt_generator(monkeypatch):
    from src.engines.editorial_engine import EditorialEngine
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType
    
    state = NarrativeState()
    state.last_processed_chapter = 1
    
    # Setup character with goals, fears, traits
    char_entry = {
        "canonical_name": StateEntry(key="canonical_name", element_type=NarrativeElementType.CHARACTER),
        "goals": StateEntry(key="goals", element_type=NarrativeElementType.CHARACTER),
        "fears": StateEntry(key="fears", element_type=NarrativeElementType.CHARACTER),
        "personality_traits": StateEntry(key="personality_traits", element_type=NarrativeElementType.CHARACTER),
    }
    char_entry["canonical_name"].update(StateSnapshot(value="Arthur", chapter=1))
    char_entry["goals"].update(StateSnapshot(value="Unify Albion", chapter=1))
    char_entry["fears"].update(StateSnapshot(value="Failure", chapter=1))
    char_entry["personality_traits"].update(StateSnapshot(value=["brave"], chapter=1))
    state.characters["arthur"] = char_entry

    # Merlin needs to be a real character entry, not just a relationship-key reference —
    # ContextRetriever's relationship tier only surfaces a relationship when BOTH parties
    # are "active" (in state.characters AND mentioned in raw_text), matching how it works
    # for the LLM extraction stages too.
    merlin_entry = {
        "canonical_name": StateEntry(key="canonical_name", element_type=NarrativeElementType.CHARACTER),
    }
    merlin_entry["canonical_name"].update(StateSnapshot(value="Merlin", chapter=1))
    state.characters["merlin"] = merlin_entry

    # Setup active relationship
    rel_entry = {
        "relationship_label": StateEntry(key="relationship_label", element_type=NarrativeElementType.CHARACTER)
    }
    rel_entry["relationship_label"].update(StateSnapshot(value="ALLIANCE", chapter=1))
    state.relationships["arthur::merlin"] = rel_entry

    # Mock LLM provider to capture the prompt
    captured_messages = []
    class MockLLM:
        is_available = True
        provider_name = "mock"
        model = "mock-model"
        def chat(self, messages):
            nonlocal captured_messages
            captured_messages = messages
            return "[]"

    engine = EditorialEngine()
    monkeypatch.setattr(engine, "_llm", MockLLM())

    # raw_text must actually mention both characters for ContextRetriever to consider
    # them active (see the comment above about the relationship tier).
    engine.review(state, None, raw_text="Chapter 1 content. Arthur spoke with Merlin.")

    assert len(captured_messages) > 0
    prompt_content = captured_messages[1]["content"]

    # Assert that all required context is in the prompt payload
    assert "Chapter 1 content." in prompt_content
    assert "Arthur" in prompt_content
    assert "Unify Albion" in prompt_content
    assert "Failure" in prompt_content
    assert "brave" in prompt_content
    assert "ALLIANCE" in prompt_content


def test_editorial_critique_carries_cross_chapter_history(monkeypatch):
    """Phase 8 deliverable: the critique must reason over accumulated history (chapter
    summaries, recent timeline), not just the current chapter in isolation. The prior
    implementation never included either — this proves both actually reach the prompt."""
    from src.engines.editorial_engine import EditorialEngine
    from src.models.state import StateEntry, StateSnapshot, NarrativeElementType

    state = NarrativeState()
    state.last_processed_chapter = 3

    name_entry = StateEntry(key="canonical_name", element_type=NarrativeElementType.CHARACTER)
    name_entry.update(StateSnapshot(value="Arthur", chapter=1))
    state.characters["arthur"] = {"canonical_name": name_entry}

    state.chapter_summaries = {
        1: "Arthur pulled the sword from the stone.",
        2: "Arthur was crowned king amid growing unrest.",
    }
    state.timeline = [
        {"chapter": 1, "subject": "arthur", "predicate": "draws", "object": "excalibur"},
        {"chapter": 2, "subject": "arthur", "predicate": "crowned_at", "object": "camelot"},
    ]

    captured_messages = []

    class MockLLM:
        is_available = True
        provider_name = "mock"
        model = "mock-model"
        def chat(self, messages):
            nonlocal captured_messages
            captured_messages = messages
            return "[]"

    engine = EditorialEngine()
    monkeypatch.setattr(engine, "_llm", MockLLM())

    engine.review(state, None, raw_text="Arthur faced the first rebellion of his reign.")

    prompt_content = captured_messages[1]["content"]
    assert "Arthur pulled the sword from the stone." in prompt_content
    assert "Arthur was crowned king amid growing unrest." in prompt_content
    assert "draws excalibur" in prompt_content
    assert "crowned_at camelot" in prompt_content
    assert "Thematic Pacing Drift" in prompt_content
    assert "Stylistic Variance" in prompt_content


