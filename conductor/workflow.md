# Workflow — Narrative Intelligence Engine

## TDD policy

**Moderate.** Tests are encouraged for new engines, memory modules, and
inspectors, but not a hard pre-implementation gate. This matches the
existing suite's coverage pattern: core logic (state engine, memory,
pipeline, editorial inspectors, context retriever, end-to-end) is tested —
74 tests across `tests/test_engines.py`, `test_memory.py`, `test_pipeline.py`,
`test_context_retriever.py`, `test_end_to_end.py` — while glue/wiring code
(API routes, frontend components) is exercised more informally. New
inspectors or memory subsystems should get real test coverage; small UI or
wiring changes don't need to block on tests first.

## Commit strategy

**Descriptive, no enforced format.** Matches the existing git history —
plain descriptive commit messages, often with concrete before/after
evidence (e.g. "cut mystery/clue noise from 56→4 entries", or naming the
specific regression fixed and why). No Conventional Commits prefix
required. Prefer messages that explain *why* a change was made over what
changed line-by-line — the diff already shows the latter.

## Code review

Follow whatever the repository's actual collaboration setup requires at
the time (this is currently a single-developer project per the git
history — adjust this section if that changes).

## Verification checkpoints

**After each phase.** This mirrors how the project has actually been
built: phased, evidence-backed commits (pipeline → state engine →
editorial layer → API → frontend), each verified before moving to the
next phase rather than after every micro-task or only at the very end of
a track. For a Conductor track, this means: implement a phase, run the
relevant test subset (`pytest tests/ -q` for backend logic touching
pipeline/engines/memory; manual UI check via the Vite dev server for
frontend phases), confirm it holds, then proceed.

## Task lifecycle

1. Understand the relevant existing subsystem before extending it (see
   [[tech-stack]] for the architectural flow — most work fits into
   pipeline → engines → memory → review → api → frontend).
2. Implement the phase.
3. Run targeted verification (`pytest tests/ -q` and/or a real pipeline
   run against sample chapters in `data/chapters/`, and/or the frontend
   dev server for UI changes).
4. Fix anything the verification surfaces.
5. Commit with a descriptive message.
6. Move to the next phase.

## Known process notes

- The project maintains a `master_context_summary.md` at the repo root
  summarizing overall status — keep it reasonably in sync with major
  phase completions, without turning it into a changelog of every commit.
- `origin/main` currently lags local `main` — pushing is a standing task,
  not a per-track requirement, unless a track's own scope says otherwise.
