# Implementation Plan: Connected Story Graph + Zero-Shot Theme/Mystery Detection

**Track ID:** story-graph-detectors_20260815
**Spec:** [spec.md](./spec.md)
**Created:** 2026-08-15
**Status:** [x] Complete

## Overview

Two independent phases, each independently verifiable and shippable:
Phase 1 wires new graph edges purely from existing persisted state (no
new dependency, low risk). Phase 2 adds the optional zero-shot classifier
and wires it into theme/symbol/mystery/clue detection with a hard
fallback to current behavior. Phase 3 is cross-cutting verification.

## Phase 1: Connected Story Graph (character↔world, character↔theme edges)

Add a helper to compute each entity's "active chapters" from its
`StateEntry` history, then use it to derive two new edge types in
`NarrativeGraph.build()`.

### Tasks

- [x] Task 1.1: Add `_entity_active_chapters(entity_fields: dict) -> set[int]`
      to `src/engines/narrative_graph.py` — walks every `StateEntry` in an
      entity's field dict via `_field_chapters`, collects chapters from
      `get_trajectory()` (StateEntry objects) or `current`/`history` dict
      keys (raw JSON), returns the union. (Plan named the accessor
      `.trajectory`; actual API is `get_trajectory()` — caught by the new
      unit test failing against the real `StateEntry` class, fixed.)
- [x] Task 1.2: In `build()`, compute active-chapter sets for every
      character and every world element once (`char_chapters`,
      `world_chapters` dicts) before the edge loops.
- [x] Task 1.3: Emit `character↔world` edges (`type: 'character_world'`)
      for every character/world pair with non-empty chapter intersection;
      edge `label` lists the shared chapters (e.g. `"ch. 1, 2"`).
- [x] Task 1.4: Emit `character↔theme` edges (`type: 'character_theme'`)
      using each theme/symbol's existing `chapters_present` field
      intersected with each character's active-chapter set (falls back to
      the theme's own active-chapter union if `chapters_present` is
      missing).
- [x] Task 1.5: Guard against edge explosion — empty-set pairs are
      skipped naturally by the intersection check. Dropped the originally
      planned "skip chapter-0-only overlaps" rule: chapter 0 is the real
      prologue in this dataset, not a sentinel value, so excluding it
      would have discarded genuine edges.

### Verification

- [x] New unit test `test_character_world_and_theme_edges` in
      `tests/test_engines.py::TestNarrativeGraph` builds a synthetic
      `NarrativeState` with 2 characters, 2 world elements, 1 theme with
      overlapping/non-overlapping chapters and asserts expected edges
      exist/don't exist by id.
- [x] Ran `NarrativeGraph.build()` against the real
      `data/memory/narrative_state.json`: 413 nodes, 826 edges total —
      `character_world: 127`, `character_theme: 340`, `relationship: 14`,
      `event_chapter: 345`. Well under the theoretical all-pairs max
      (22 chars × 16 world = 352; 22 chars × ~29 theme/symbol categories
      ≈ 638), confirming real co-occurrence filtering, not an all-to-all
      blowup.
- [x] `pytest tests/ -q` — 75 passed (74 existing + 1 new).

## Phase 2: Zero-shot theme/mystery/symbol/clue detection with fallback

### Tasks

- [x] Task 2.1: Created `src/utils/zero_shot_classifier.py` — a
      `ZeroShotClassifier` class with lazy singleton model load
      (`transformers.pipeline("zero-shot-classification",
      model="facebook/bart-large-mnli")`), a `classify_batch(texts, labels,
      multi_label=True) -> list[dict[str, float]] | None` method, and an
      `available` property. Any import/load/runtime exception is caught
      once (`_load_attempted` guard), logged at warning level, and
      permanently flips `available` to `False` for the process lifetime.
      Verified live: in this sandboxed dev environment `transformers`/
      `torch` ARE installed but there's no working internet (SSL cert
      failure reaching huggingface.co) — the wrapper correctly falls back
      to `available: False` after one ~10s load attempt rather than
      raising or retrying per-call.
- [x] Task 2.2: Added `transformers`/`torch` to `requirements.txt` as a
      commented-out optional block, matching the existing "later phase
      dependencies" section style.
- [x] Task 2.3: Updated `ThemeMemory._detect_themes` — added
      `_count_hits_via_classifier`/`_count_hits_via_keywords` helpers;
      when the classifier is available, batch-classifies
      `chapter_data.sentences` against human-readable theme labels
      (`ZERO_SHOT_THEME_THRESHOLD = 0.6`), producing the same
      `{name: count}` shape the keyword path always produced, so the rest
      of `_detect_themes` (the `MIN_MENTIONS_TO_INTRODUCE` gate,
      `description` generation, `StateChange` emission) is untouched.
- [x] Task 2.4: Same pattern applied to `ThemeMemory._detect_symbols`
      using `SYMBOL_KEYWORDS` keys as labels.
- [x] Task 2.5: Updated `MysteryMemory._extract_mysteries` — semantic
      check (label "poses an unresolved mystery or question",
      `ZERO_SHOT_MYSTERY_THRESHOLD = 0.75`) added as an additional way
      `matched_indicator` can be set, after the existing keyword/question
      checks.
- [x] Task 2.6: Same pattern for `_extract_clues` (label "reveals a clue
      or piece of evidence") and `_check_revelations` (label "resolves or
      reveals a secret", still gated by `_mentions_mystery` word-overlap
      to stay specific to the right mystery). Implementation detail vs.
      plan: all three methods now share a single batched classifier call
      per chapter (`MysteryMemory._classify_sentences`, invoked once from
      `update_from_chapter`) rather than three separate calls — same
      per-sentence label scores, 3x fewer classifier invocations.
- [x] Task 2.7: Confirmed no module-level `transformers`/`torch` import
      anywhere — only inside `ZeroShotClassifier._ensure_loaded()`.
      `theme_memory.py`/`mystery_memory.py` only import
      `get_classifier` from our wrapper.

### Verification

- [x] New `tests/test_zero_shot_classifier.py`: forces the unavailable
      path via a monkeypatched `transformers` module (no real download
      needed) and confirms `ThemeMemory`/`MysteryMemory` still detect via
      the keyword baseline; separately mocks `classify_batch` with canned
      scores and confirms classifier-driven detection fires on sentences
      with *no* literal keyword match, correctly gated by threshold, and
      still emits the same `StateChange` shape.
- [x] `pytest tests/ -q` — 82 passed (75 after Phase 1 + 7 new), including
      in this dev environment where `transformers`/`torch` are installed
      (confirms the network-failure fallback path also works, not just
      the not-installed path).
- [ ] Real end-to-end run through an actual downloaded
      `facebook/bart-large-mnli` model was not possible in this sandbox
      (no outbound internet access — verified above). Fallback behavior
      is fully verified; true zero-shot output quality is unverified
      pending a network-enabled environment. Flagging as a follow-up
      check rather than blocking the track.

## Phase 3: Cross-cutting verification & docs

### Tasks

- [x] Task 3.1: Updated `master_context_summary.md` — "Theme/Mystery/
      Symbol detection" row now describes the hybrid keyword+zero-shot
      status with the fallback behavior explained; "Richer story graph"
      bullet under "Potential Extensions" marked done with real edge
      counts; test count updated (52→73→75→82); added a new bullet
      flagging zero-shot output quality as unverified pending network
      access.
- [x] Task 3.2: Regenerated `data/memory/narrative_graph.json` (the API
      serves this pre-built file, not a live rebuild — `api/graph_data.py`
      just reads it) and visually verified in a real running instance:
      started the API (`uvicorn api.main:app --port 8420`, matching
      `frontend/vite.config.ts`'s proxy target — note: port 8000 was
      already occupied by an unrelated pre-existing process on this
      machine, unrelated to this project) and the frontend
      (`npm run dev`), opened `/graph` in the browser. New character↔world
      and character↔theme edges render correctly via the existing generic
      edge-drawing logic — no frontend code change needed. Confirmed via
      hover tooltip: a character with no character↔character relationship
      data ("his_daughter") now shows "10 Connections" through the new
      co-occurrence edges alone. Both dev servers stopped after
      verification.

### Final Verification

- [x] All acceptance criteria in spec.md met.
- [x] `pytest tests/ -q` — 82 passed (74 baseline + 1 graph edge test +
      7 zero-shot classifier tests).
- [x] `master_context_summary.md` updated.
- [x] Ready for review / commit.

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
