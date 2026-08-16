# Specification: Self-Review Bug Fixes

**Track ID:** self-review-fixes_20260816
**Type:** Bug
**Created:** 2026-08-16
**Status:** Complete

## Summary

An overnight autonomous session, after landing the story-graph/zero-shot/
contextual-lookback features, used idle time to run `/code-review` passes
(one over the night's diff, one over `src/engines`) per the loop's own
guidance ("sweeping the branch for issues is a good use of that time").
Six real, verified bugs surfaced — some pre-existing, some introduced
earlier the same night — all fixed here.

## Bugs found and fixed

1. **Story Graph node labels showed raw IDs, not display names**
   (`src/engines/narrative_graph.py`). Pre-existing. `_entry_value()` was
   called on an entity's whole fields-dict instead of the specific field
   holding the display name, so it always fell through to the raw id.
   Directly undermined the character↔world/character↔theme edges added
   earlier tonight. New `_entity_label()` helper, regression test added.

2. **Duplicate zero-shot classifier calls per chapter**
   (`src/memory/theme_memory.py`). Introduced tonight. `_detect_themes`/
   `_detect_symbols` each independently classified the same sentences,
   doubling ~1.6GB BART-MNLI inference cost for no benefit. Merged into
   one shared `classify_batch` call via `update_from_chapter`.

3. **`ArcInspector._check_unresolved_arcs` never called**
   (`src/review/arc_inspector.py`). Pre-existing. Fully implemented,
   named in `inspect()`'s own docstring as an implemented rule, but never
   wired into `inspect()` — the "unresolved arc near story end" finding
   silently never fired. No existing test relied on the missing
   behavior. Fixed and covered with a new regression test.

4. **Non-deterministic mystery/conflict IDs via builtin `hash()`**
   (`src/engines/state_engine.py`, 4 call sites). Pre-existing. Python's
   `hash()` on strings is randomized per-process (`PYTHONHASHSEED`)
   unless pinned — no pinning exists in this repo. Re-running the
   pipeline over the same chapter would produce different IDs each time,
   duplicating (rather than updating) the same logical mystery/conflict
   in `narrative_state.json`. Switched to the project's own
   `stable_hash()` utility (already used the same way in
   `mystery_memory.py`), truncated to 4 hex chars to match the previous
   ID length/collision space.

5. **Relationship mutation parties not resolved to canonical character IDs**
   (`src/engines/state_engine.py`). Pre-existing. The `character_updates`
   loop resolves the LLM's raw name/casing through
   `character_memory.resolve_character_id` before touching state;
   `relationship_mutations` did not, so an already-established character
   (`laurie`) mentioned with different casing (`"Laurie"`) in a
   relationship proposal would fail the `party in current_state.characters`
   check and create a second, divergent relationship record
   (`"Laurie::Marlene"` alongside `"laurie::marlene"`). Now resolves both
   parties the same way `character_updates` does.

6. **Dual-ownership inventory check missed first-time assignments**
   (`src/engines/narrative_state.py::reconcile_state_changes`).
   Pre-existing. Only checked `EVOLUTION`/`CONTRADICTION` change types, so
   two characters each getting the same item for the first time in one
   chapter (both `INTRODUCTION`) were never cross-checked. Added
   `INTRODUCTION` to the gated change types.

7. **Silent scene-analysis failures**
   (`src/engines/narrative_state.py`). Pre-existing. A bare
   `except Exception: pass` around scene detection/analysis discarded any
   failure with zero diagnostic output, leaving `chapter_data.scenes`
   silently unset. Added a `logger.warning` with the chapter number and
   exception.

8. **Path traversal / arbitrary-write in the chapter upload endpoint**
   (`api/main.py`, `POST /api/ingest`). Found by manual reading, not an
   automated review pass. The upload's `file.filename` (fully attacker-
   controlled) was joined straight into a filesystem path with only the
   extension checked. Confirmed by direct repro:
   `Path("data/chapters") / "../../../../evil.txt"` escapes the intended
   directory, and `Path("data/chapters") / "C:\Windows\System32\evil.txt"`
   **silently discards the base directory entirely** (pathlib's `/`
   operator returns the right operand outright when it's absolute) --
   an absolute-path filename would write anywhere the process has
   permissions. New `_safe_upload_filename()` reduces the filename to
   `Path(...).name` before any path join. First tests for the `api/`
   layer (`tests/test_api.py`), 5/5 passing.

## Acceptance Criteria

- [x] All 7 bugs above fixed at their root cause, not worked around.
- [x] Regression tests added for the two silently-broken *behavioral*
      bugs (node labels, unresolved-arc finding) where none existed.
- [x] No regression: full test suite green after all fixes.
- [x] Fixes verified against real data where practical (graph node labels
      checked against the actual committed `narrative_state.json`).

## Out of Scope

- The `_is_evidence_supported` bidirectional-substring matching in
  `ValidationEngine` (no word-boundary safety) was noted during review as
  a minor, low-severity heuristic risk (short mention hints could
  false-positive) but not changed — no concrete failure scenario, unlike
  the 7 bugs above, and changing matching heuristics without a real
  observed failure risks its own regressions.
- A broader `src/pipeline`, `src/review` (remaining 6 inspectors), and
  `src/memory` (remaining 6 modules) review pass was not completed —
  the first attempt at a 3-directory review stalled/failed after 10
  minutes; a narrower `src/engines`-only retry succeeded. Worth a
  follow-up pass.

## Technical Notes

The `narrative_graph.json` export was regenerated after the label fix
(node counts unchanged: 413 nodes / 826 edges, only labels changed).
