# 📖 Narrative Intelligence Engine (NIE) 🧠

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![NLP Stack](https://img.shields.io/badge/NLP-spaCy%20%7C%20GLiNER%20%7C%20FastCoref-orange.svg?style=for-the-badge)](https://spacy.io/)
[![LLM Engines](https://img.shields.io/badge/LLMs-Gemini%20%7C%20Groq%20%7C%20Ollama-red.svg?style=for-the-badge)](https://google.ai/)
[![Visualizer](https://img.shields.io/badge/Visuals-Vis.js%20%7C%20NetworkX-success.svg?style=for-the-badge)](https://visjs.org/)
[![Tests](https://img.shields.io/badge/Tests-100%25%20Passing-brightgreen.svg?style=for-the-badge)](https://pytest.org/)

> **"Raw text is just noise. Evolving story-graph memory is the signal."**  
> Welcome to the future of developmental book editing. The **Narrative Intelligence Engine** is a computational developmental editor designed to read, analyze, and track the evolution of complex, multi-chapter novels. By representing narrative memory as a stateful, chronological knowledge graph, the engine knows everything important about Chapters 1–99 by the time it reaches Chapter 100—without re-reading a single line of text.

---

## ⚡ The Architectural Blueprint

Unlike simple chat interfaces or generic vector retrieval tools that lose track of context over long texts, the Narrative Intelligence Engine splits **Sensory Ingestion** (observations) from **Narrative Understanding** (beliefs), feeding state updates into an editorial reasoning core.

```
       📖 Raw Chapter Text (PDF, DOCX, TXT)
                        │
                        ▼
┌──────────────────────────────────────────────┐
│            SENSORY NLP PIPELINE              │
│   • spaCy: tokenization, syntax, SVO parsing │
│   • GLiNER: zero-shot Named Entity tagging   │
│   • FastCoref: coreference resolution        │
│   • Dialogue: quote isolation & attribution  │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│           STRUCTURED EVIDENCE                │
│    ChapterData JSON (Observable Facts)       │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│          NARRATIVE STATE ENGINE              │
│   Processes evidence, determines delta, and  │
│   propagates transitions to narrative memory │
└───────────────────────┬──────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
┌─────────────────┐           ┌─────────────────┐
│  STORY MEMORY   │           │EDITORIAL ENGINE │
│  Characters     │           │  8 Inspectors   │
│  Relationships  │           │  (Pacing, Arc,  │
│  World Lore     │           │  Voice, Conflict│
│  Timeline       │           │  Timeline, etc.)│
│  Themes         │           │        +        │
│  Promises       │           │  LLM Critique   │
└────────┬────────┘           └────────┬────────┘
         │                             │
         ▼                             ▼
┌─────────────────┐           ┌─────────────────┐
│ NARRATIVE GRAPH │           │EDITORIAL REPORT │
│ Vis.js HTML Web │           │Plot inconsistencies│
│   Interactive   │           │ pacing & motives│
└─────────────────┘           └─────────────────┘
```

---

## 🔥 Features that Sound Cool AF

### 🧠 1. Stateful Evolving Memory (Chronological Versioning)
Story elements are alive. We don't overwrite character details or plot lines; we model their **evolution**. Every character, relationship, and setting contains a versioned history of state transitions, supported by confidence scores, reasoning, and chapter evidence markers. 
*   **Characters**: Tracks dynamic goals, deep-seated fears, emotional states, physical traits, possessions, and story arc stages.
*   **Relationships**: Records interactive events, mapping trust metrics and bidirectional stances (e.g. Rivals ➜ Lovers ➜ Nemeses).
*   **Promises & Mysteries**: Monitors foreshadowing, setups, and open questions, throwing alerts if they remain unresolved near the climax.

### 🔍 2. Deep Editorial Inspectors (Static & LLM Hybrid)
Nine custom-tailored static inspectors scrutinize your story's data structure to flag plot holes:
*   **Arc Inspector**: Evaluates character progression through structural beats (Introduction, Rising Action, Climax, Resolution).
*   **Pacing Inspector**: Analyzes dialogue density, scene length, and action ratios.
*   **Voice Inspector**: Tracks syntactical rhythm, average sentence lengths, and stylistic drift.
*   **Timeline Inspector**: Detects temporal shifts, flashbacks, and chronological gaps.
*   **Spatiotemporal Inspector**: Flags characters in two places at once or impossible travel times.
*   *Plus Scene, Conflict, Relationship, and Character Inspectors.*
*   **Signal triage**: Inspector output is grouped before anything reads it. Nine detectors emitting one finding per offending entity is the right granularity for a detector and the wrong one for a report — an early chapter-3 report was 81 findings of which 50 were the same note repeated once per entity. `src/review/signal_triage.py` collapses those into distinct signals with a count and exemplars, and deliberately does *not* let priority scale with repetition: fifty identical notes are one observation, usually an over-eager rule rather than fifty story problems.
*   **LLM Critique**: A fallback-resilient LLM reviewer (Gemini → Groq → Ollama, auto-failover) adds thematic evaluation, grounded in a token-budgeted `ContextRetriever` context block rather than raw text alone.
*   **LLM Synthesis**: A second pass ranks the grouped signals *and* the critique's own findings together, verifies them against the chapter, merges duplicates, drops detector noise, and writes a prose developmental-editor letter plus 3–7 ranked `top_findings` carrying `why_it_matters` and a concrete `recommendation`. This is what turns a flat list of detector output into a review. Reports also carry `key_events` — with a deterministic fallback derived from the curated timeline, so a failed or non-compliant LLM response can never silently ship a report with the chapter's beats missing.
*   **ValidationEngine**: Gates every LLM-authored proposal (new character, world item, relationship) against deterministic NLP evidence before it reaches state — rejects unsupported entities and flags field-level contradictions instead of silently trusting the LLM.

### ⚡ 3. Blazing Fast NLP Caching
No more waiting on heavy models. The pipeline hashes chapter texts with **SHA-256**. If a chapter hasn't changed, cached evidence is returned instantly—dropping processing times from **60–90 seconds to under 0.1 seconds**!

### 🔌 4. Zero-Dependency LLM Routing
Built completely with Python's standard library (`urllib.request` + `json`), the engine automatically auto-detects and prioritizes your available LLM backends:
1.  **Gemini** (`gemini-2.0-flash`)
2.  **Groq** (`openai/gpt-oss-120b`)
3.  **Ollama** (`llama3` running locally)

### 🎨 5. Stunning Interactive Graph Visualizer
Transform raw data into art. The visualizer compiles the NetworkX story relationships and outputs a standalone, interactive HTML file (`narrative_graph.html`) built with **Vis.js**.
*   Drag, zoom, and dynamic physics layout.
*   **Color Coded**: **Blue** for Characters, **Green** for Locations, **Yellow** for Events, **Purple** for Themes, **Gray** for Chapters.
*   Interactive details pane updates on node selection.

---

## 🛠️ Setup & Kickstart

### 📦 Installation

1. Clone the repo and navigate to the project directory:
   ```bash
   cd Narrative_Engine
   ```

2. Spin up a virtual environment and activate it:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. Install requirements and download the base NLP model:
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

4. Configure your environment (Optional for LLM critiques):
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY="your-gemini-api-key"
   # OR
   GROQ_API_KEY="your-groq-api-key"
   ```

---

## 🚀 Running the Engine

### Ingest and Analyze a Chapter
Run the end-to-end processing pipeline over any raw text, DOCX, or PDF chapter:
```bash
python src/main.py --chapter path/to/chapter.txt
```

### Inspect Current Narrative State
Get a high-level summary of your evolving novel's graph statistics:
```bash
python src/main.py --status
```

### Launch the Visualization
Generate the gorgeous network graph from your current memory:
```bash
python scripts/visualize_graph.py
```
*Open `data/memory/narrative_graph.html` in any browser to interact with the narrative network!*

---

## 📂 Project Anatomy

```
Narrative_Engine/
├── src/
│   ├── pipeline/       # NLP Sensory Pipeline (Parser, Cleaner, NER, Coref, Dialogue)
│   ├── models/         # Core State & Evidence Dataclasses
│   ├── memory/         # Stateful Memories (Character, Relationship, World, Theme, etc.)
│   ├── engines/        # Reasoning Cores (Narrative State, Scene, Editorial, Graphs)
│   ├── review/         # Rule-based Critique Inspectors
│   └── utils/          # Config & LLM Provider abstractions
├── tests/              # 100% covered Test Suite
├── config/             # YAML configurations
├── data/
│   ├── memory/         # Saved JSON states, reports, and interactive HTML files
│   └── cache/          # Cached NLP extraction packets
└── scripts/            # Visualizer scripts & setup tools
```

---

## 🧪 Bulletproof Testing

The project has a robust testing suite running 93 unit and integration tests. Run them instantly:
```bash
pytest
```

---

## ⚠️ Known Limitations (honest status, updated 2026-07-30)

The core architecture — deterministic NLP evidence → grounded LLM interpretation → validated state → editorial critique — is fully wired and tested end-to-end. What's still rough:

*   **Theme/mystery/symbol detection is hybrid: keyword-based by default, zero-shot when available (2026-08-15).** `src/utils/zero_shot_classifier.py` wraps a `transformers` zero-shot-classification pipeline (`facebook/bart-large-mnli`) that, when installed and reachable, batch-classifies sentences against theme/symbol/mystery/clue/revelation labels as a semantic signal alongside the existing keyword gates. `transformers`/`torch` are optional (commented out in `requirements.txt`, ~1.6GB) — the engine falls back automatically and deterministically to the original keyword logic when they're absent or the model can't be reached, so nothing is required to run the core engine.
*   **VADER sentiment and textstat readability are now live** — `sentiment_compound` (VADER) is computed per-scene and per-chapter alongside the existing keyword-based emotional tone label, and `flesch_reading_ease`/`flesch_kincaid_grade` (textstat) are computed in chapter style metrics. Dialogue attribution has real turn-taking inference (alternates between the two known speakers in a scene when a quote's speaker is otherwise unresolved) in addition to the speech-tag regex. **Still missing**: BookNLP, LanguageTool, and any DistilRoBERTa-style emotion classifier — those roles remain custom heuristics/regex, not the mature OSS libraries originally scoped.
*   **Coreference now feeds character attribution directly.** FastCoref's real mention spans and sentence spans are carried through `ChapterData` (previously computed and discarded), and character trait/goal/fear/etc. extraction is attributed via a per-chapter sentence→character map built from literal name matches plus resolved coreference clusters (with LLM disambiguation fallback) — replacing the old unused `coref_map` parameter.
*   **LLM backend priority is Gemini → Groq → Ollama** with automatic failover on error, but a Gemini project with an exhausted/zero quota will still burn ~60s retrying with exponential backoff before failing over — check quota status if chapter processing feels slow.
*   **Contextual lookback across chapter breaks (2026-08-16).** `NarrativeState` now carries the previous chapter's raw-text tail (`previous_chapter_excerpt`) forward, and `ContextRetriever` surfaces it as a fixed `<PreviousChapterExcerpt>` context tier — LLM extraction stages get direct continuity across a chapter break, not just structured state fields.
*   **Not yet validated at real scale.** Everything so far has run on a small number of chapters; confidence decay, dormancy tracking, and reconciliation logic are implemented but unverified across a 50-100 chapter novel.
*   **Web dashboard exists now, and has been exercised end-to-end with a real chapter upload** (`api/` FastAPI backend + `frontend/` React/TypeScript SPA) — browses every tracked collection (characters, relationships, world, themes/motifs, promises/mysteries/threats, conflicts/arcs, style/readability metrics), the timeline, editorial reports, an interactive force-directed Story Graph (canvas + `d3-force`, built from `narrative_graph.json`), and chapter ingestion with live job-status polling and job history — all backed by the canonical `narrative_state.json`/report/graph files rather than a separate database. Every `StateSnapshot`'s `evidence_ids` resolve to real evidence text via `GET /api/evidence`, expandable inline. Not yet load-tested at real novel scale. The Story Graph now also carries character↔world and character↔theme edges (2026-08-15/16, derived from chapter co-occurrence, tinted by connected node type) — world/theme nodes are no longer islands. Run with `uvicorn api.main:app --port 8420` (backend — `--reload`'s file-watcher has been unreliable on Windows in testing; restart manually after backend edits) and `npm run dev` in `frontend/` (Vite dev server, proxies `/api` to 8420).

---
*Created with 💙 for writers, editors, and computational narrative engineers.*
