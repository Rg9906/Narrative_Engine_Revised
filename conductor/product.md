# Product Definition — Narrative Intelligence Engine

## What it is

A computational developmental editor for novels. Instead of re-feeding raw
chapter text to an LLM on every pass (which loses context on long
manuscripts and re-derives the same facts repeatedly), the engine builds a
**persistent, versioned "story memory"** — characters, relationships, world
lore, timeline, themes, and promises/foreshadowing (Chekhov's-gun tracking)
— and updates it incrementally as each chapter is ingested. By chapter 100
it "knows" everything established in chapters 1–99 without re-reading them.

An editorial layer then runs 9 rule-based inspectors plus LLM critique over
that memory to flag plot holes, pacing problems, inconsistent
characterization, dangling promises, and other continuity errors — the kind
of thing a human developmental editor tracks across an entire manuscript.

## Problem statement

Long-form fiction (novels, serials) accumulates a huge amount of
interdependent state — who knows what, who's related to whom, what's been
promised to the reader, how a character's arc has evolved — that is
expensive and unreliable to hold in an LLM's context window chapter after
chapter. Authors and editors have no good way to mechanically track
continuity, consistency, and craft issues (pacing, voice drift, unresolved
promises) across a full manuscript without manually re-reading it.

## Target users

Authors generally — a tool other novelists can run on their own
manuscripts, not just a bespoke tool for one project. The current sample
data (a 4-chapter detective/mystery manuscript) is a working demonstration
of the pipeline, not the target content itself.

## Key goals (current)

1. Push the current local work (FastAPI backend + React frontend, 7 commits
   ahead of `origin/main`) to the remote.
2. Scale-test the pipeline and state engine on a full-length manuscript
   (50–100 chapters) — the confidence-decay/dormancy/reconciliation logic
   is implemented but only exercised on 4 chapters so far.
3. Replace remaining keyword-heuristic detectors (theme/mystery/symbol
   detection) with more principled classifiers, per the original vision
   doc's USE/WRAP/EXTEND/BUILD plan.

## Origin

The project has a formal spec predating implementation:
`Project Vision.docx` / `Project Structure.docx` (see `doc_extract.txt`),
which map each cognitive task (character modeling, relationships,
timeline, worldbuilding, themes, style) to a specific tool decision and a
phased implementation roadmap. The codebase follows that spec closely; see
[[tech-stack]] for what was actually adopted vs. deferred.
