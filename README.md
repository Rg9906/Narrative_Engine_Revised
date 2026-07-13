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
Eight custom-tailored static inspectors scrutinize your story's data structure to flag plot holes:
*   **Arc Inspector**: Evaluates character progression through structural beats (Introduction, Rising Action, Climax, Resolution).
*   **Pacing Inspector**: Analyzes dialogue density, scene length, and action ratios.
*   **Voice Inspector**: Tracks syntactical rhythm, average sentence lengths, and stylistic drift.
*   **Timeline Inspector**: Detects temporal shifts, flashbacks, and chronological gaps.
*   *Plus Scene, Conflict, Relationship, and Character Inspectors.*
*   **LLM Critique**: Uses a fallback-resilient LLM reviewer to add deep thematic evaluations.

### ⚡ 3. Blazing Fast NLP Caching
No more waiting on heavy models. The pipeline hashes chapter texts with **SHA-256**. If a chapter hasn't changed, cached evidence is returned instantly—dropping processing times from **60–90 seconds to under 0.1 seconds**!

### 🔌 4. Zero-Dependency LLM Routing
Built completely with Python's standard library (`urllib.request` + `json`), the engine automatically auto-detects and prioritizes your available LLM backends:
1.  **Gemini** (`gemini-2.0-flash`)
2.  **Groq** (`llama-3.3-70b-versatile`)
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

The project has a robust testing suite running 52 unit and integration tests. Run them instantly:
```bash
pytest
```

---
*Created with 💙 for writers, editors, and computational narrative engineers.*
