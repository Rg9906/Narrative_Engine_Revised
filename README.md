# Narrative Intelligence Engine

A computational system that reads and *understands* long novels the way a seasoned developmental editor does. It builds an evolving narrative state — tracking characters, relationships, world rules, themes, conflicts, promises, arcs, and more — so that by Chapter 100, it already knows everything important from Chapters 1–99.

## Philosophy

- **Raw text is never the sole source of analysis.** The NLP pipeline extracts *evidence*; the Narrative State Engine interprets evidence into *understanding*.
- **Nothing is static.** Every piece of state models evolution — with history, evidence, confidence, and reasoning.
- **Think like a developmental editor.** The system remembers what a human editor remembers: characters, promises, foreshadowing, pacing, voice, unresolved questions.

## Architecture

```
Raw Chapter Text
       │
       ▼
  NLP Pipeline (evidence extraction)
  spaCy · GLiNER · FastCoref · BookNLP
       │
       ▼
  Structured Evidence (ChapterData)
       │
       ▼
  Narrative State Engine (THE HEART)
  Interprets evidence → state transitions
       │
       ▼
  Evolving Narrative State
  Characters · Relationships · World · Timeline · Themes · Promises · Arcs
       │
       ▼
  Editorial Engine
  Reasons over state, not text
  Consistency · Arcs · Pacing · Promises · Style
```

## Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Usage

```bash
python src/main.py --chapter path/to/chapter.txt
```

## Project Structure

```
src/
├── pipeline/       # NLP evidence extraction
├── models/         # Core data models (Evidence, StateEntry, StateDelta, etc.)
├── memory/         # Persistent narrative state modules
├── engines/        # Narrative State Engine, Scene Engine, Editorial Engine
├── review/         # Editorial inspectors
└── utils/          # Configuration, helpers
tests/              # Automated tests
config/             # Configuration files
data/memory/        # Serialized narrative state
```

## License

MIT
