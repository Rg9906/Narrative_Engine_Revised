"""Tests for the curated-timeline split and editorial signal triage.

Both exist to fix the same class of problem: the engine was reporting mechanical
volume as if it were narrative substance. The timeline was 345 rows of which 337
were dependency-parser output, and a chapter's editorial report was 81 findings of
which 50 were one rule firing repeatedly.
"""

from src.engines.editorial_engine import EditorialEngine
from src.models.state import NarrativeState, StateDelta, split_timeline_feeds
from src.review.signal_triage import group_signals, render_signals_for_prompt


class TestTimelineSplit:
    def test_legacy_state_is_partitioned_on_load(self):
        """A state file written before the split has raw triples inlined in `timeline`
        and no `raw_relations` key. It must become readable without a full reprocess."""
        legacy = [
            {"chapter": 0, "subject": "world", "predicate": "moved", "object": "sound"},
            {"chapter": 0, "subject": "Marlene", "predicate": "dipped", "object": "brush"},
            {
                "chapter": 3, "subject": "sergeant_rhodes", "predicate": "arrives",
                "object": "at the house", "source": "llm_timeline_stage",
            },
            {"chapter": 3, "subject": "jamie", "predicate": "moves_to", "object": "the kitchen"},
        ]

        curated, raw = split_timeline_feeds(legacy, None)

        assert [e["subject"] for e in curated] == ["sergeant_rhodes", "jamie"]
        assert [e["subject"] for e in raw] == ["world", "Marlene"]
        assert curated[0]["kind"] == "narrative"
        assert curated[1]["kind"] == "structural"

    def test_already_split_state_passes_through(self):
        curated_in = [{"chapter": 1, "kind": "narrative", "summary": "A thing happens."}]
        raw_in = [{"chapter": 1, "subject": "a", "predicate": "b", "object": "c"}]

        curated, raw = split_timeline_feeds(curated_in, raw_in)

        assert curated == curated_in
        assert raw == raw_in

    def test_empty_raw_relations_list_is_not_treated_as_missing(self):
        """An explicitly empty raw_relations list means 'already split, nothing raw' —
        it must not trigger the migration and re-partition the curated feed."""
        curated_in = [{"chapter": 1, "subject": "x", "predicate": "wanders", "object": "y"}]

        curated, raw = split_timeline_feeds(curated_in, [])

        assert curated == curated_in
        assert raw == []

    def test_narrative_state_roundtrips_both_feeds(self):
        state = NarrativeState()
        state.timeline = [{"chapter": 1, "kind": "narrative", "summary": "A thing happens."}]
        state.raw_relations = [{"chapter": 1, "subject": "a", "predicate": "b", "object": "c"}]

        restored = NarrativeState.from_dict(state.to_dict())

        assert restored.timeline == state.timeline
        assert restored.raw_relations == state.raw_relations


class TestSignalTriage:
    def _repeated(self, count, title="Abrupt mystery resolution"):
        return [
            {
                "severity": "note",
                "category": "conflict",
                "title": title,
                "description": f"Instance {i}",
                "related_entities": [f"mystery_{i}"],
                "confidence": 0.7,
            }
            for i in range(count)
        ]

    def test_repeated_finding_collapses_to_one_signal(self):
        signals = group_signals(self._repeated(50))

        assert len(signals) == 1
        assert signals[0]["count"] == 50
        assert len(signals[0]["examples"]) == 3
        assert signals[0]["suppressed_count"] == 47

    def test_priority_does_not_scale_with_repetition(self):
        """Fifty identical notes are one observation repeated, not fifty problems. A
        single error must still outrank them — this is the exact inversion that buried
        chapter 3's real findings under 50 duplicate notes."""
        findings = self._repeated(50) + [
            {
                "severity": "error",
                "category": "consistency",
                "title": "Canonical name inconsistency",
                "description": "Two names for one character.",
                "confidence": 1.0,
            }
        ]

        signals = group_signals(findings)

        assert signals[0]["title"] == "Canonical name inconsistency"
        assert signals[0]["priority"] > signals[1]["priority"]

    def test_large_group_is_flagged_as_probable_detector_noise(self):
        signals = group_signals(self._repeated(50))
        assert signals[0]["likely_detector_noise"] is True

        signals = group_signals(self._repeated(2))
        assert signals[0]["likely_detector_noise"] is False

    def test_group_takes_highest_severity_of_its_members(self):
        """Grouping must never quietly downgrade a real error into a note."""
        findings = [
            {"severity": "note", "category": "c", "title": "T", "description": "a"},
            {"severity": "error", "category": "c", "title": "T", "description": "b"},
        ]

        signals = group_signals(findings)

        assert len(signals) == 1
        assert signals[0]["severity"] == "error"

    def test_rendered_prompt_block_warns_about_noisy_groups(self):
        rendered = render_signals_for_prompt(group_signals(self._repeated(50)))

        assert "fired 50x" in rendered
        assert "miscalibrated" in rendered
        assert "+47 further instances" in rendered

    def test_rendering_handles_no_signals(self):
        assert "no rule-based signals" in render_signals_for_prompt([])


class TestKeyEventsFallback:
    """The chapter-3 report shipped with key_events silently empty. The fallback exists
    so a failed or non-compliant critique call can never erase the chapter's beats."""

    def _state_with_events(self):
        state = NarrativeState()
        state.last_processed_chapter = 3
        state.timeline = [
            {"chapter": 3, "kind": "narrative", "summary": "Rhodes brings news of a witness.", "significance": 0.9},
            {"chapter": 3, "kind": "narrative", "summary": "Jamie makes coffee.", "significance": 0.4},
            {"chapter": 3, "kind": "structural", "summary": "jamie moves to the kitchen"},
            {"chapter": 3, "kind": "structural", "summary": "Whitmore dies at the house", "reader_facing": True},
            {"chapter": 2, "kind": "narrative", "summary": "An earlier chapter's beat.", "significance": 1.0},
        ]
        return state

    def test_derives_events_ordered_by_significance(self):
        engine = EditorialEngine()
        events = engine._key_events_from_timeline(self._state_with_events(), StateDelta(chapter_number=3))

        assert events[0] == "Rhodes brings news of a witness."
        assert "Jamie makes coffee." in events

    def test_excludes_other_chapters_and_non_reader_facing_markers(self):
        engine = EditorialEngine()
        events = engine._key_events_from_timeline(self._state_with_events(), StateDelta(chapter_number=3))

        assert "An earlier chapter's beat." not in events
        assert "jamie moves to the kitchen" not in events
        # A death is structural but genuinely a story beat, so it is reader-facing.
        assert "Whitmore dies at the house" in events

    def test_returns_empty_when_chapter_has_no_curated_events(self):
        engine = EditorialEngine()
        state = NarrativeState()
        state.last_processed_chapter = 9
        state.raw_relations = [{"chapter": 9, "subject": "world", "predicate": "moved", "object": "sound"}]

        assert engine._key_events_from_timeline(state, StateDelta(chapter_number=9)) == []


class TestChapterDataCaching:
    """The pipeline caches the whole ChapterData and returns it before running any NLP or
    LLM stage. `llm_delta` was assigned as an ad-hoc attribute that `to_dict` never
    serialized, so every cache hit silently replayed the chapter deterministic-only — no
    character updates, no relationship mutations, no timeline events, no consistency
    check. The only trace was an INFO line reading "No LLM delta for chapter N"."""

    def test_llm_delta_survives_a_serialization_roundtrip(self):
        from src.models.state import ChapterData

        chapter_data = ChapterData(chapter_number=3)
        chapter_data.llm_delta = {
            "character_updates": [{"character_id": "jamie"}],
            "timeline_events": [
                {"subject": "sergeant_rhodes", "predicate": "arrives", "significance": 0.8}
            ],
            "structural_mysteries": [],
        }

        restored = ChapterData.from_dict(chapter_data.to_dict())

        assert restored.llm_delta == chapter_data.llm_delta
        assert restored.llm_delta["timeline_events"][0]["significance"] == 0.8

    def test_llm_delta_defaults_to_empty_dict_for_legacy_cache_entries(self):
        """Cache files written before llm_delta was serialized have no such key."""
        from src.models.state import ChapterData

        restored = ChapterData.from_dict({"chapter_number": 1})

        assert restored.llm_delta == {}

    def test_cache_key_includes_the_extraction_version(self):
        """Without this, changing an extraction prompt leaves every already-processed
        chapter serving stale evidence, and the new code looks like it did nothing."""
        from src.pipeline import pipeline as pipeline_module

        assert isinstance(pipeline_module.EXTRACTION_VERSION, int)

        import inspect

        source = inspect.getsource(pipeline_module.Pipeline.process_chapter)
        assert "EXTRACTION_VERSION" in source


class TestExtractionStageSizeHandling:
    """The extraction stages must survive a backend that rejects large prompts, by
    sending less rather than by silently producing nothing."""

    def test_trimming_removes_only_the_story_context_block(self):
        from src.pipeline.llm_extraction import LLMExtractionEngine

        system_content = (
            "PREAMBLE\n\n<StoryContext>accumulated background</StoryContext>\n\n"
            "<DeterministicEvidence>entities and relations</DeterministicEvidence>"
        )

        trimmed = LLMExtractionEngine._trim_context_block(system_content)

        assert "accumulated background" not in trimmed
        # The evidence the stage is actually reasoning over must survive.
        assert "entities and relations" in trimmed
        assert "PREAMBLE" in trimmed

    def test_trimming_is_a_noop_without_a_context_block(self):
        from src.pipeline.llm_extraction import LLMExtractionEngine

        content = "PREAMBLE with no context block"
        assert LLMExtractionEngine._trim_context_block(content) == content

    def test_truncation_keeps_the_output_schema(self):
        """Cutting the chapter text must never cut the instructions that tell the model
        what shape to answer in."""
        from src.pipeline.llm_extraction import LLMExtractionEngine

        prompt = "CHAPTER " + ("x" * 9000) + "--- Output Requirements ---\nSCHEMA HERE"

        truncated = LLMExtractionEngine._truncate_chapter_text(prompt, keep_chars=2000)

        assert len(truncated) < len(prompt)
        assert "SCHEMA HERE" in truncated
        assert "truncated" in truncated

    def test_short_prompts_are_left_alone(self):
        from src.pipeline.llm_extraction import LLMExtractionEngine

        prompt = "short\n--- Output Requirements ---\nSCHEMA"
        assert LLMExtractionEngine._truncate_chapter_text(prompt) == prompt

    def test_stage_retries_smaller_then_gives_up_cleanly(self, monkeypatch):
        """A stage that cannot be made to fit returns {} rather than raising, so one
        oversized stage never aborts the chapter."""
        from src.pipeline.llm_extraction import LLMExtractionEngine
        from src.utils.llm_provider import RequestTooLargeError

        engine = LLMExtractionEngine()
        calls = []

        def always_too_large(system_content, prompt, raise_too_large=False):
            calls.append(len(system_content) + len(prompt))
            raise RequestTooLargeError("413")

        monkeypatch.setattr(engine, "_fetch_json", always_too_large)

        result = engine._run_stage(
            "world_timeline_scene",
            "P\n\n<StoryContext>" + ("c" * 3000) + "</StoryContext>",
            "CH " + ("x" * 9000) + "--- Output Requirements ---\nSCHEMA",
        )

        assert result == {}
        # Full, context-trimmed, then context-trimmed + text-truncated.
        assert len(calls) == 3
        assert calls[0] > calls[1] > calls[2]

    def test_stage_succeeds_on_the_trimmed_retry(self, monkeypatch):
        from src.pipeline.llm_extraction import LLMExtractionEngine
        from src.utils.llm_provider import RequestTooLargeError

        engine = LLMExtractionEngine()
        attempts = {"n": 0}

        def too_large_once(system_content, prompt, raise_too_large=False):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RequestTooLargeError("413")
            return {"timeline_events": [{"subject": "a", "predicate": "arrives"}]}

        monkeypatch.setattr(engine, "_fetch_json", too_large_once)

        result = engine._run_stage(
            "world_timeline_scene",
            "P\n\n<StoryContext>ctx</StoryContext>",
            "CH text\n--- Output Requirements ---\nSCHEMA",
        )

        assert result["timeline_events"][0]["predicate"] == "arrives"
        assert attempts["n"] == 2
