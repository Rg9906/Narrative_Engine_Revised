# Specification: Connected Story Graph + Zero-Shot Theme/Mystery Detection

**Track ID:** story-graph-detectors_20260815
**Type:** Feature
**Created:** 2026-08-15
**Status:** Draft

## Summary

Two self-contained upgrades identified as the next concrete phase in
`master_context_summary.md`'s own "Completion Status" and "Potential
Extensions" sections: (1) wire real character↔world and character↔theme
edges into the Story Graph so it's actually connected instead of showing
disconnected node clusters, and (2) replace keyword-heuristic theme/
mystery/symbol detection with zero-shot NLI classification
(`facebook/bart-large-mnli` via `transformers`), while keeping the
existing keyword logic as an automatic fallback when the model isn't
available (no internet, dependency not installed) so the test suite and
any lightweight deployment keep working unchanged.

## Context

Per [[product]] and [[tech-stack]], this project's core bet is
evidence-backed, versioned narrative state feeding an editorial layer and
a dashboard. The Story Graph page in `frontend/` already renders
character, world, theme, event, and chapter nodes via d3-force, but
`NarrativeGraph.build()` (`src/engines/narrative_graph.py`) only emits
character↔character relationship edges and event→chapter edges — world
and theme nodes are currently islands. Separately, `ThemeMemory` and
`MysteryMemory` (`src/memory/`) detect themes/symbols/mysteries/clues via
fixed keyword lists with noise-reduction gates added in a prior hardening
pass (2026-07-28) — functional, but not the topic-modeling/zero-shot
approach the original vision doc specified.

## User Story

As an author using the dashboard, I want the Story Graph to show how
characters relate to the world elements and themes active in the chapters
they appear in, and I want theme/mystery detection to catch things
phrased without the exact keyword list, so that the tool surfaces
connections and narrative signals a purely literal keyword match would
miss.

## Acceptance Criteria

- [ ] `NarrativeGraph.build()` emits character↔world edges: a character
      and a world element are connected if they share at least one
      "active chapter" (derived from `StateEntry.trajectory`/
      `last_mentioned_chapter` across all fields of each entity — no new
      evidence plumbing required).
- [ ] `NarrativeGraph.build()` emits character↔theme edges: a character
      is connected to a theme/symbol if the character has an active
      chapter within that theme's existing `chapters_present` field.
- [ ] Edge counts stay reasonable (no accidental all-to-all explosion) —
      verified against the existing 3-4 chapter sample data.
- [ ] A new `src/utils/zero_shot_classifier.py` provides a lazily-loaded,
      singleton wrapper around a `transformers` zero-shot-classification
      pipeline (`facebook/bart-large-mnli`), batching sentence
      classification per chapter for performance.
- [ ] The wrapper degrades gracefully and deterministically: if
      `transformers`/`torch` aren't installed, or model load fails for
      any reason (no internet, OOM, etc.), it marks itself unavailable
      once and every caller falls back to the existing keyword-based
      logic — no exceptions propagate, no partial/mixed state.
- [ ] `ThemeMemory._detect_themes` / `_detect_symbols` use zero-shot
      sentence classification against the existing theme/symbol category
      names (as human-readable labels) when the classifier is available,
      feeding into the *same* downstream logic (`MIN_MENTIONS_TO_INTRODUCE`
      gate, `description` generation, `StateChange` emission) — falls
      back to the current substring-count logic otherwise.
- [ ] `MysteryMemory` adds classifier-based sentence labeling ("poses an
      unresolved mystery/question", "reveals a clue or evidence",
      "resolves/reveals a secret", "ordinary narration") as an additional
      *semantic* signal alongside (not replacing) the existing explicit
      keyword/question-mark checks, gated by a conservative confidence
      threshold to avoid reopening the mystery/clue noise problem fixed
      on 2026-07-28.
- [ ] `requirements.txt` documents `transformers`/`torch` as an optional,
      commented-out "heavier NLP" dependency block (matching the existing
      "later phase dependencies" pattern), not a hard requirement.
- [ ] All 74 existing tests still pass unmodified in an environment
      without `transformers` installed (the default/CI case).
- [ ] New unit tests cover: the classifier wrapper's fallback behavior
      (mocked/forced-unavailable path), and the new graph edge logic
      against a small synthetic `NarrativeState`.

## Dependencies

- Depends on existing `src/engines/narrative_graph.py`,
  `src/memory/theme_memory.py`, `src/memory/mystery_memory.py`,
  `src/models/state.py` (`StateEntry`/`StateSnapshot`/`NarrativeState`).
- No dependency on other incomplete tracks.

## Out of Scope

- Scale-testing on a 50–100 chapter manuscript (no such manuscript exists
  yet — separate track once content is available).
- BookNLP / LanguageTool integration (larger, separate effort per the
  vision doc's remaining scope).
- Pushing local commits to `origin/main` (administrative, not
  implementation work).
- Changing the frontend Story Graph rendering itself — new edge types
  should render using the existing generic edge-drawing logic; a
  dedicated visual treatment per edge type is a possible future track.
- Applying zero-shot classification to any subsystem other than
  theme/symbol/mystery/clue/revelation detection (e.g. not touching
  character trait extraction, arc inspection, etc. in this track).

## Technical Notes

- Zero-shot approach chosen over the lighter sentence-embedding option
  after explicit tradeoff discussion: `facebook/bart-large-mnli` is a
  ~1.6GB download and CPU inference is meaningfully slower than the
  existing keyword scan, but it gives true zero-shot label classification
  rather than similarity-based approximation. This is acceptable because
  (a) the project already has per-chapter SHA-256 result caching so the
  cost is paid once per chapter, and (b) the fallback path keeps
  lightweight/CI/offline usage working exactly as today.
- Graph edges are derived purely from already-persisted `NarrativeState`
  (chapter co-occurrence via `StateEntry` history) — no changes to
  `ChapterData`/evidence plumbing are needed for this track.

---

_Generated by Conductor. Review and edit as needed._
