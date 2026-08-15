# Tech Stack — Narrative Intelligence Engine

Detected from the existing repository (brownfield project). Versions are
lower-bound constraints from `requirements.txt` / `package.json` unless
noted.

## Backend / core engine (Python)

- **Language:** Python (3.x; no explicit pin found — check local venv)
- **NLP pipeline:**
  - `spacy` (>=3.7,<4.0) — tokenization, dependency parsing
  - `gliner` (>=0.2) — zero-shot/generalist NER
  - `fastcoref` (>=2.1) — coreference resolution, feeds pronoun-based
    character attribution
  - `python-docx`, `pymupdf` — manuscript ingestion (docx/pdf)
- **Style/emotion analysis:** `textstat` (readability), `vaderSentiment`
  (lexicon-based sentiment) — offline, no model download
- **Graph:** `networkx` (>=3.2) — narrative graph construction, exported
  for d3-force visualization
- **LLM extraction:** provider-agnostic via `src/utils/llm_provider.py`,
  with failover chain Gemini → Groq → Ollama (see `config/default.yaml`
  and `.env.example` for provider config)
- **API server:** `fastapi` (>=0.110) + `uvicorn[standard]` — thin read
  layer over `data/*.json`, plus background-task chapter ingestion
- **Config:** `pyyaml`, `dataclasses-json`
- **Testing:** `pytest` (>=8.0) — 74 tests passing as of last verification

**Deferred/not yet integrated** (noted in `requirements.txt` as
"later phase"): `bookNLP`, `sentence-transformers`. The original vision
doc scoped BookNLP and LanguageTool as USE-AS-IS integrations that were
never wired in — theme/mystery detection uses custom heuristics instead.

## Frontend

- **Framework:** React 19.2 + TypeScript ~6.0, built with Vite 8.1
- **Data fetching:** `@tanstack/react-query` 5.x — real `fetch` calls
  against the FastAPI backend (`frontend/src/lib/api.ts`), no mocked data
- **UI:** Radix UI primitives (accordion, dialog, dropdown, tabs, tooltip,
  switch, progress), Tailwind CSS 4.x, `framer-motion`, `lucide-react`
  icons, `sonner` for toasts
- **Graph visualization:** `d3-force` for the interactive story graph
- **Routing:** `react-router-dom` 7.x
- **Linting:** `oxlint` (see `frontend/.oxlintrc.json` — react + typescript
  + oxc plugins, `react/rules-of-hooks` enforced)

## Storage

No database. All state persists as JSON files under `data/` (profiles,
relationships, clues, promises, narrative_graph.json, narrative_state.json,
editorial reports). Writes are atomic (`BaseMemory.save()` writes to a
`.tmp` file and `os.replace`s it). Job tracking for chapter ingestion is
in-memory, single-process (`api/jobs.py`) — acceptable for local/dev use,
would not survive a restart or multiple workers.

## Infrastructure

Self-hosted / local. No deployment target has been set up — `uvicorn` dev
server for the API, `vite` dev server for the frontend. No Docker, no
cloud config present. Revisit this file if/when a deployment target is
chosen.

## Key architectural flow

```
Chapter text
  → Pipeline (spaCy + GLiNER NER + FastCoref coref + dependency-parsed
     relations + dialogue extraction + VADER/textstat)      [src/pipeline/]
  → ChapterData (deterministic evidence)
  → NarrativeStateEngine (evidence-first, then gated LLM extraction
     via Gemini→Groq→Ollama failover, validated by ValidationEngine)
                                                              [src/engines/]
  → NarrativeState (versioned, append-only StateEntry/StateSnapshot
     per field, with confidence + reasoning + evidence_ids)  [src/models/]
  → EditorialEngine (9 inspectors: char, relationship, scene, conflict,
     pacing, timeline, spatiotemporal, arc, voice + LLM critique)
                                                              [src/review/]
  → editorial_report_ch{N}.json + narrative_graph.json + narrative_state.json
  → FastAPI read layer                                       [api/]
  → React dashboard                                          [frontend/]
```
