# Product Guidelines — Narrative Intelligence Engine

## Voice and tone

Friendly and approachable. This applies to user-facing text in the
dashboard (frontend/), error messages, and onboarding/help copy. Internal
code comments, docstrings, and technical docs (README, this Conductor
context) can stay precise and evidence-oriented — that split already
exists in the codebase (module docstrings are technical; the dashboard UI
should read as approachable to non-technical authors).

## Design principles

- **Evidence over inference.** The core architectural bet of this project:
  deterministic NLP evidence (spaCy/GLiNER/FastCoref extraction) gates
  what the LLM is allowed to claim, enforced by `ValidationEngine`, which
  rejects LLM-proposed entities unsupported by deterministic evidence. New
  subsystems (inspectors, memory modules, extraction stages) should keep
  extending this discipline rather than trusting raw LLM output.
- **Incremental, versioned state.** Memory is append-only —
  `StateEntry`/`StateSnapshot` history is never overwritten, only added to,
  with confidence + reasoning + evidence_ids per snapshot. Preserve this
  pattern in any new memory subsystem; don't introduce mutation-in-place
  shortcuts.
- **Replace heuristics with principled models over time.** Theme/mystery/
  symbol detection is currently keyword-heuristic. Treat this as ongoing
  technical debt to pay down, not a permanent design choice — prioritize
  swapping in real classifiers (per the original vision doc's tool
  choices) as capacity allows.
- **Scale-readiness.** Design new work with 50–100 chapter manuscripts in
  mind, not just the current 4-chapter sample. Dormancy tracking,
  reconciliation, and confidence decay exist specifically for this; don't
  regress them for convenience on small inputs.

See [[workflow]] for how these principles translate into day-to-day
development practice (TDD strictness, verification checkpoints).
