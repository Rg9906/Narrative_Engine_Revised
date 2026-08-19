# Master Context — Narrative Intelligence Engine

The **Narrative Intelligence Engine** is a computational developmental editor designed to read, analyze, and track the evolution of complex, multi-chapter novels. Instead of running LLM reasoning over raw text (which loses context over long texts), it converts text into structured evidence, builds a versioned story memory, and critiques the narrative using rule-based inspectors and LLMs.

---

## 1. Subsystem Architecture & Data Flow

```mermaid
flowchart TD
    A[Raw Chapter Text: PDF/DOCX/TXT] --> B[Document Parser & Cleaner]
    B --> C[Sensory NLP Pipeline: spaCy + GLiNER + FastCoref]
    C --> D[Evidence: ChapterData JSON]
    
    subgraph Narrative Memory Store
        D --> E[Narrative State Engine]
        E --> F[Characters Memory]
        E --> G[Relationships Memory]
        E --> H[World Settings Memory]
        E --> I[Timeline & Themes]
        E --> J[Promises & Mysteries]
    end
    
    subgraph Editorial Engine & Visualizer
        F & G & H & I & J --> K[Static Rule Inspectors]
        F & G & H & I & J --> L[LLM Developmental Critique]
        F & G --> M[NarrativeGraph Builder]
        
        K & L --> N[Editorial Report JSON]
        M --> O[Interactive HTML Visualizer]
    end
```

### The Three Pillars:
1.  **Evidence vs. State**: The **Sensory Pipeline** extracts observations (what was seen). The **Narrative State Engine** translates this into beliefs (what is understood). 
2.  **Chronological Versioning**: Every piece of narrative memory (e.g., character goals or traits) is stored as a `StateEntry` containing a historical list of `StateSnapshot` objects. Values are never simply overwritten; they preserve reasoning, confidence scores, and supporting evidence.
3.  **Editorial Inspections**: The **Editorial Engine** checks for plot holes, pacing gaps, voice changes, underdeveloped characters, and dangling promises without re-reading the raw text.

---

## 2. Recent Implementations & Hardening

*   **Hybrid deterministic + LLM state pipeline**: GLiNER/FastCoref/dependency-parsed relations/dialogue now run as the PRIMARY evidence source before any LLM call (fixing an earlier regression where chapters were fed to the LLM directly, bypassing the NLP layer). LLM extraction is split into four grounded stages (character/relationship, world/timeline, thematic, consistency-checker) that read the deterministic evidence plus a token-budgeted `ContextRetriever` context block — never raw text alone.
*   **Curated timeline vs. raw relation evidence (2026-08-17)**: `NarrativeState.timeline` used to receive every dependency-parsed subject-verb-object triple, so the "timeline" was 345 rows of which 337 were parser output (`world moved sound`, and one row per verb/object pair, so a single sentence produced three) and only 8 were real events. The two feeds are now separate: `timeline` holds curated beats (`kind: "narrative"` — LLM-authored, with `summary`/`participants`/`location`/`event_type`/`significance`/`why_it_matters`/`causes` — plus `kind: "structural"` markers like `moves_to`/`dies` that inspectors depend on), and `raw_relations` holds the triples. `split_timeline_feeds()` partitions legacy state files on load, so an un-reprocessed `narrative_state.json` reads correctly without a rebuild. The World+Timeline LLM stage is now capped at 8 beats/chapter, must justify each with a `why_it_matters` clause, and self-scores `significance`; `StateEngine` drops anything under `MIN_EVENT_SIGNIFICANCE`.
*   **Real mention counts (2026-08-17)**: `mention_count` was incremented once per *deduplicated surface form* per chapter, so it counted spellings, not mentions — Marlene, the POV character of the entire prologue, scored 1, and `CharacterInspector` reported her as "only mentioned 1 time(s)... consider increasing presence". It is now computed in `CharacterMemory._update_presence_counts` from the coreference-resolved sentence map (so pronoun-only sentences count), alongside a new `mentions_this_chapter` and an honest `chapters_present`. `CharacterInspector` additionally now only flags a thin character once they have survived past the chapter that introduced them.
*   **Editorial signal triage + LLM synthesis pass (2026-08-17)**: chapter 3's report was 81 flat findings — 50 identical "Abrupt mystery resolution" notes, 16 "only mentioned 1 time(s)", 6 from the LLM — with nothing ranking them and `key_events` silently empty. Now: `src/review/signal_triage.py` groups inspector output into distinct signals (81 → 17 on that report) whose priority is severity×confidence and explicitly does *not* scale with repetition, flagging groups over 12 as likely detector miscalibration; then a second LLM pass (`EditorialEngine._run_synthesis`) ranks those signals together with the critique's findings, verifies them against the chapter, merges duplicates, and emits `editorial_letter`, `strengths`, and 3–7 `top_findings` with `why_it_matters`/`recommendation`/`subsumes`. `key_events` has a deterministic fallback from the curated timeline so it can never silently ship empty.
*   **Extraction now fits a token-budgeted provider (2026-08-17)**: the Groq account is free-tier, capped at **8,000 tokens per minute**, while each extraction prompt (raw chapter text + `ContextRetriever` block + deterministic evidence + schema) runs 6,000-9,000 tokens. Two things made that fatal rather than merely slow. (1) Stages A/B/C ran *concurrently* via a `ThreadPoolExecutor`, issuing ~18k tokens at once — correct for a latency-bound workload, exactly wrong for a token-bound one; they now run sequentially. (2) An oversized request returns **HTTP 413**, which the failover logic treated as a structural failure and used to retire the backend for the whole run — so one long chapter disabled the LLM for every later stage, including the editorial critique and synthesis. 413 now raises `RequestTooLargeError`, which retires nothing and is never retried unchanged; instead the caller retries with less input (`LLMExtractionEngine._run_stage` drops `<StoryContext>`, then truncates the chapter text; `EditorialEngine._chat_with_size_retry` truncates the chapter text). TPM 429s now also honour the server's own "try again in 34.5s" hint instead of blind exponential backoff. Practical consequence: on the free tier a chapter needs ~6 sequential LLM calls against an 8k/min budget, so expect several minutes per chapter — a paid Groq tier or a Gemini project with real quota is the actual fix for throughput.

*   **NLP cache is now version-keyed (2026-08-17)**: `data/cache/` stores the *entire* `ChapterData`, including `llm_delta`, and the pipeline returns it before running NER, coreference, dialogue extraction, or any LLM stage. Keyed on the text hash alone, that made extraction improvements invisible on any already-processed chapter — reprocessing replayed the old evidence and the old LLM proposals verbatim, so a rebuild intended to pick up the new timeline prompt produced an empty curated timeline instead. The key now includes `Pipeline.EXTRACTION_VERSION` (currently 2); bump it whenever a change would yield different `ChapterData` for identical input text.

*   **The LLM layer was entirely dead (2026-08-17)**: Groq's `llama-3.3-70b-versatile` had been decommissioned and returned HTTP 404 ("model does not exist"), while the Gemini project reports `quota_limit_value: "0"` and returns 429 — so *every* LLM call in the engine failed over to a dead model and degraded to empty output, which the code swallowed silently (each stage returns `{}` on failure by design). Default Groq model moved to `openai/gpt-oss-120b`; verify with `GET https://api.groq.com/openai/v1/models`, as Groq retires models regularly. `LLMProvider` now records hard-failed backends process-wide (`_dead_backends`) instead of each of a chapter's ~6 stages independently burning five exponential-backoff retries (~60s) rediscovering the same exhausted quota, and reports *why* a backend failed rather than a bare "HTTP Error 404: Not Found".

*   **ValidationEngine**: Gatekeeper between LLM proposals and canonical state — rejects new entities unsupported by deterministic evidence, applies a confidence floor, and checks field-level contradictions before writing (physical traits, status, ownership) rather than reverting after the fact.
*   **ContextRetriever**: Single-source-of-truth RAG-style context hydration from the live `NarrativeState` (or canonical `narrative_state.json` on cold start) — four-tier surgical hydration (characters, relationships, promises, world) plus themes/motifs/chapter summaries/recent timeline, token-budgeted to ~6000 chars.
*   **Noise reduction in deterministic memory (2026-07-28)**: `MysteryMemory` no longer flags bare wh-words ("who/what/why/how" appearing anywhere) or generic perception verbs ("saw", "found", "realized") as mysteries/clues — it now requires real question-punctuated sentences or strong explicit phrases ("mystery", "baffled", "remains a mystery"). `ThemeMemory` requires 2+ distinct keyword signals before introducing a brand-new theme/symbol category, and now auto-populates a `description` field for each theme/symbol instead of leaving it empty. On the 3 real chapters processed so far this cut mystery/clue noise from 56→4 entries and theme/symbol noise from 25→14, without losing genuine signal.
*   **Real sentiment & readability (2026-07-29)**: VADER (`sentiment_compound`) now runs per-scene (`scene_engine.py`) and per-chapter (`pipeline.py`) alongside the existing keyword-based emotional tone label — additive, not a replacement. `textstat` computes `flesch_reading_ease`/`flesch_kincaid_grade` in chapter style metrics.
*   **Turn-taking speaker inference (2026-07-29)**: `DialogueExtractor` adds a second pass — when a scene has exactly two known speakers (from speech-tag regex) and a quote's speaker is otherwise unresolved, it infers the other speaker via alternation (`turn_taking_inferred`, confidence 0.45). Deliberately skips scenes with 0, 1, or 3+ known speakers.
*   **Physical trait extraction fix (2026-07-29)**: `character_memory.py:_extract_trait_value` previously grabbed whatever word sat adjacent to an anchor noun ("hair", "eyes"); it now scans the sentence for an actual self-describing descriptor word (e.g. "blonde", "tall") and returns `None` rather than fabricating a value when none qualifies.
*   **Real FastCoref spans through the pipeline (2026-07-29)**: `ExtractedCoreferenceCluster.mention_spans` and `ChapterData.sentence_spans` are now populated and serialized (previously computed and discarded). Character attribution (traits, goals, fears, arc stage, inventory, location) is now driven by a per-chapter sentence→character map built from literal name matches plus resolved coreference clusters (LLM disambiguation fallback for unmatched clusters) — replacing the old, effectively-unused `coref_map` parameter on extraction methods.
*   **Test Suite**: All **93 unit and integration tests are passing** (grew from 52 as ValidationEngine/ContextRetriever/9-inspector EditorialEngine were added, to 73 with the coreference-attribution and trait-extraction fixes, to 75 with the story-graph edge tests, to 82 with the zero-shot classifier fallback/behavior tests, to 86 with the contextual-lookback tests, then to 93 with the arc-inspector/dual-ownership regression tests and the first `api/` layer tests — 2026-08-16. Full suite confirmed green: 93/93 in 96s. This number will keep moving; check `pytest -q` for the live count rather than trusting this doc).
*   **NLP Pipeline Caching**: SHA-256 caching mechanism in [pipeline.py](file:///c:/Users/RG%20Saran%20Vishakan/Desktop/Narrative_Engine/src/pipeline/pipeline.py) saves evidence packages to `data/cache/`, reducing subsequent chapter processing times from **60–90 seconds to under 0.1 seconds**.
*   **Vis.js Interactive Graph Visualizer**: `scripts/visualize_graph.py` transforms exported NetworkX graphs into a self-contained, drag-and-zoom network HTML file.
*   **Automatic `.env` Loader**: `src/utils/config.py` auto-loads credentials from `.env` on launch. LLM backend priority is Gemini → Groq → Ollama with automatic failover — note that a Gemini project with zero/exhausted quota will still spend ~60s retrying with exponential backoff before failing over to Groq.

---

## 3. How the Engine Functions & Outputs

### Core Input:
*   A chapter file (`.txt`, `.pdf`, or `.docx`) containing narrative text.

### Key Outputs (Located in `data/memory/`):
1.  **`narrative_state.json`**: The complete, serialized narrative memory containing character sheets, relationship matrices, world elements, and a timeline.
2.  **`editorial_report_ch{N}.json`**: A developmental report compiling:
    *   *Static Findings*: E.g., characters undergoing shifts without enough interaction, dead characters performing actions, or unresolved timeline events.
    *   *LLM Findings*: Deep cognitive critiques covering pacing, thematic execution, and motivation.
3.  **`narrative_graph.html`**: A Vis.js-powered visual editor workspace showing the story network (Characters = Blue, World/Locations = Green, Events = Yellow/Orange, Themes = Purple, Chapters = Gray).

---

## 4. Completion Status (honest, updated 2026-07-29)

| Feature Area | Status | Notes |
| :--- | :--- | :--- |
| **Sensory NLP pipeline (GLiNER + FastCoref + dependency relations + dialogue)** | Complete | Runs as primary evidence before any LLM call. |
| **Evolving Narrative Memory & base handlers** | Complete | Full StateEntry/StateSnapshot versioning with history. |
| **Hybrid LLM extraction + StateEngine + ValidationEngine** | Complete | Two-pass (deterministic baseline, then gated LLM refinement). |
| **ContextRetriever (RAG-style context hydration)** | Complete | Single source of truth, token-budgeted. |
| **Automated Inspectors (9) & Editorial critique** | Complete | Rule-based + LLM critique with cross-chapter context. |
| **NLP Pipeline Caching** | Complete | SHA-256 keyed. |
| **Interactive HTML Network visualizer** | Complete | Vis.js. |
| **Coreference-driven character attribution** | Complete | Real FastCoref mention/sentence spans carried through `ChapterData`; per-chapter sentence→character map (name match + resolved clusters, LLM disambiguation fallback) drives trait/goal/fear/arc extraction, replacing the old unused `coref_map` param. |
| **Sentiment (VADER) & readability (textstat)** | Complete | `sentiment_compound` per-scene/per-chapter alongside existing keyword tone; `flesch_reading_ease`/`flesch_kincaid_grade` in chapter style metrics. |
| **Dialogue turn-taking inference** | Complete | Second pass in `DialogueExtractor` alternates between the two known speakers in a scene for otherwise-unresolved quotes (confidence 0.45); skips 0/1/3+ speaker scenes. |
| **Theme/Mystery/Symbol detection** | Hybrid — keyword + optional zero-shot (2026-08-15) | `src/utils/zero_shot_classifier.py` wraps a `transformers` zero-shot-classification pipeline (`facebook/bart-large-mnli`) that, when available, batch-classifies sentences against theme/symbol/mystery/clue/revelation labels; falls back automatically (and deterministically — one load attempt, then cached `available=False`) to the original keyword+noise-reduction-gate logic when `transformers`/`torch` aren't installed or the model can't be reached. `transformers`/`torch` are optional, commented-out deps in `requirements.txt` — not required to run the engine. |
| **BookNLP, LanguageTool, DistilRoBERTa-style emotion classifier** | Not implemented | Vision docs scoped these as USE-AS-IS libraries; current code uses custom heuristics/regex plus VADER/textstat instead. |
| **Scale validation (50-100+ chapters)** | Not done | Only a handful of real chapters processed so far. |
| **Web GUI Dashboard** | Built + verified end-to-end (2026-07-31) | FastAPI (`api/`) + React/TypeScript/Tailwind SPA (`frontend/`) covering every collection (characters, relationships, world, themes/motifs, promises/mysteries/threats, conflicts/arcs, style), timeline, editorial reports, evidence-of-claim drill-down, an interactive `d3-force` Story Graph, and chapter ingestion with job history. A real chapter was ingested through the actual UI/API path (Ch. 3, 112 state changes, 81 findings, Gemini→Groq failover) confirming the full pipeline → state → editorial → graph → UI loop works. Not committed to git yet as of this writing; not load-tested at real novel scale. |

### Realistic overall completion: ~80-85% of the original vision.
The hard architectural work (evidence/state separation, hybrid deterministic+LLM grounding, validation gating, editorial reasoning over state) is done and tested. What's left is mostly refinement — replacing remaining keyword heuristics with more principled models, and validating behavior at real novel-length scale — not new subsystems.

#### Potential Extensions (Future Scope):
*   ~~**Contextual Lookback**~~ — **Done (2026-08-16).** `NarrativeState` now carries `previous_chapter_excerpt`/`previous_chapter_number` (last 1500 chars of the prior chapter's raw text, set in `src/main.py` after each chapter's delta is applied). `ContextRetriever` renders it as a fixed, unconditional `<PreviousChapterExcerpt>` tier so LLM extraction stages get direct cross-chapter continuity beyond structured state fields. Verified against the real dataset and with new unit tests (live-state, disk-fallback, and omitted-when-absent cases).
*   ~~**Richer story graph**~~ — **Done (2026-08-15/16).** `NarrativeGraph.build()` now emits `character↔world` and `character↔theme` edges derived from chapter co-occurrence (each entity's active chapters, computed from its `StateEntry` history) — world and theme nodes are no longer islands. Verified against the real dataset: 413 nodes, 826 edges (127 character↔world, 340 character↔theme, 14 relationship, 345 event↔chapter), and visually confirmed in the running dashboard. Follow-up done 2026-08-16: `GraphCanvas.tsx` now tints each edge type to match the node color it connects to (world edges green, theme edges purple) instead of every non-relationship edge looking identical — visually confirmed via zoomed screenshot.
*   **Zero-shot output quality at scale**: The new zero-shot classifier path (see completion table above) has its fallback behavior fully verified, but true `bart-large-mnli` output quality is unverified — the dev sandbox has no outbound internet access to actually download the model. Worth spot-checking theme/mystery noise levels once run in a network-enabled environment.
*   **Security fix (2026-08-16): path traversal in chapter upload.** `POST /api/ingest` joined the fully attacker-controlled upload filename straight into a filesystem path with only the extension checked — a filename like `"../../evil.txt"` escaped the intended directory, and an absolute-path filename (`"C:\Windows\System32\evil.txt"`) silently discarded the base directory entirely (a pathlib `/`-operator gotcha) and would write anywhere the process has permissions. Fixed via a `_safe_upload_filename()` helper that reduces the filename to its bare basename before any path join. First tests for the `api/` layer added (`tests/test_api.py`).
