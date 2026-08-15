# Python Style Guide — Narrative Intelligence Engine

No existing lint/format config was found in the repo (no `ruff.toml`,
`.flake8`, `pyproject.toml`, or `black` config), so this guide is derived
from the conventions already visible in `src/` — follow them for
consistency rather than introducing a different style.

## Observed conventions (keep following these)

- `from __future__ import annotations` at the top of modules that use
  type hints, to allow forward references without quoting.
- Full type hints on public methods (`Optional[str]`, `Dict[str, Any]`,
  `list`, etc. from `typing`).
- Module-level docstring explaining the *purpose* of the module in
  narrative terms (what problem it solves, not just what it contains) —
  see `src/memory/base_memory.py` for the pattern.
- Class and method docstrings use Google-style `Args:`/`Returns:`
  sections, kept short.
- Logging via the standard `logging` module with a dotted logger name
  namespaced under `"NarrativeEngine.<Subsystem>.<Module>"`
  (e.g. `"NarrativeEngine.Memory.Base"`), not `print()`.
- Atomic file writes for anything under `data/`: write to a `.tmp` path
  and `os.replace()` into place, with a fallback direct-write path on
  `OSError`. Follow this pattern for any new persistence code.
- Private/internal state prefixed with a single underscore
  (`self._entries`, `self._metadata`), exposed via `@property` where
  read access is needed externally.
- f-strings for log/debug messages; avoid `%`-formatting or `.format()`.

## Recommended additions (not yet enforced, low-risk to adopt)

- If a formatter/linter is introduced, `ruff` (format + lint in one tool)
  is a reasonable default given the project has no existing tooling
  investment to migrate away from.
- Keep new modules' docstrings evidence/purpose-oriented, matching
  [[product-guidelines]]'s "evidence over inference" principle — explain
  *why* a module exists and what guarantees it provides, not just what
  functions it has.

## Testing

- Tests live under `tests/`, one file roughly per subsystem
  (`test_engines.py`, `test_memory.py`, `test_pipeline.py`,
  `test_context_retriever.py`, `test_end_to_end.py`). Follow that mapping
  for new test files rather than one file per source module.
- Run via `pytest tests/ -q`.
