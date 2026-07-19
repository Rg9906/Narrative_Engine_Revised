"""
Narrative Intelligence Engine — Main Entry Point

This is the orchestrator that ties everything together:
  1. Load configuration
  2. Initialize or restore the Narrative State
  3. Process a chapter through the NLP pipeline (evidence extraction)
  4. Feed evidence to the Narrative State Engine (state transitions)
  5. Run the Editorial Engine (reasoning over state)
  6. Persist the updated state

The flow:
  Raw Text → Evidence → State Delta → State Update → Editorial Review
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure the repository root is on path when executing src/main.py directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.state import NarrativeState
from src.utils.config import get_config
from src.pipeline.pipeline import Pipeline
from src.engines.narrative_state import NarrativeStateEngine
from src.engines.editorial_engine import EditorialEngine
from src.engines.narrative_graph import NarrativeGraph


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("NarrativeEngine")


def load_narrative_state(memory_dir: Path) -> NarrativeState:
    """Load the existing narrative state from disk, or create a fresh one."""
    state_path = memory_dir / "narrative_state.json"
    if state_path.exists():
        logger.info(f"Loading existing narrative state from {state_path}")
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return NarrativeState.from_dict(data)
    else:
        logger.info("No existing state found. Initializing fresh narrative state.")
        return NarrativeState()


def save_narrative_state(state: NarrativeState, memory_dir: Path) -> None:
    """Persist the narrative state to disk atomically."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_path = memory_dir / "narrative_state.json"
    tmp_path = state_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
    import os
    os.replace(tmp_path, state_path)
    logger.info(f"Narrative state saved to {state_path}")


def save_modular_state(state: NarrativeState, config) -> None:
    """Persist characters, relationships, clues, and promises as separate, modular files.

    These are DERIVED EXPORTS for human browsing / external tooling — e.g. opening
    data/profiles/laurie.json directly. narrative_state.json (see save_narrative_state)
    is the single canonical source of truth; nothing in this codebase reads these
    per-entity files back in. ContextRetriever (src/pipeline/context_retriever.py) reads
    only the canonical file or the live in-memory NarrativeState — never these.
    """
    import os
    
    # 1. Save character profiles to data/profiles/
    config.profiles_dir.mkdir(parents=True, exist_ok=True)
    for char_id, profile in state.characters.items():
        char_file = config.profiles_dir / f"{char_id}.json"
        tmp_file = char_file.with_suffix(".json.tmp")
        profile_dict = {
            char_id: {sk: sv.to_dict() for sk, sv in profile.items()}
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(profile_dict, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, char_file)
        logger.info(f"Profile saved: {char_file}")

    # 2. Save relationships to data/relationships/
    config.relationships_dir.mkdir(parents=True, exist_ok=True)
    for rel_key, rel_entry in state.relationships.items():
        safe_key = rel_key.replace("::", "__")
        rel_file = config.relationships_dir / f"{safe_key}.json"
        tmp_file = rel_file.with_suffix(".json.tmp")
        rel_dict = {
            rel_key: {sk: sv.to_dict() for sk, sv in rel_entry.items()}
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(rel_dict, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, rel_file)
        logger.info(f"Relationship saved: {rel_file}")

    # 3. Save promises to data/promises/
    config.promises_dir.mkdir(parents=True, exist_ok=True)
    for promise_id, promise_entry in state.promises.items():
        promise_file = config.promises_dir / f"{promise_id}.json"
        tmp_file = promise_file.with_suffix(".json.tmp")
        promise_dict = {
            promise_id: {sk: sv.to_dict() for sk, sv in promise_entry.items()}
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(promise_dict, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, promise_file)
        logger.info(f"Promise saved: {promise_file}")

    # 4. Save clues to data/clues/
    config.clues_dir.mkdir(parents=True, exist_ok=True)
    for elem_id, elem_entry in state.world.items():
        type_entry = elem_entry.get("type")
        type_val = type_entry.current.value if type_entry and type_entry.current else None
        if type_val == "object":
            clue_file = config.clues_dir / f"{elem_id}.json"
            tmp_file = clue_file.with_suffix(".json.tmp")
            clue_dict = {
                elem_id: {sk: sv.to_dict() for sk, sv in elem_entry.items()}
            }
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(clue_dict, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, clue_file)
            logger.info(f"Clue saved: {clue_file}")


def clear_subdirectories(config) -> None:
    """Recursively purges all files across all 7 subdirectories."""
    import shutil
    dirs = [
        config.chapters_dir,
        config.summaries_dir,
        config.profiles_dir,
        config.relationships_dir,
        config.clues_dir,
        config.promises_dir,
        config.reports_dir,
        config.cache_dir,
        config.memory_dir
    ]
    for d in dirs:
        if d.exists():
            for item in d.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        logger.info(f"Deleted file: {item}")
                    elif item.is_dir():
                        shutil.rmtree(item)
                        logger.info(f"Deleted dir: {item}")
                except Exception as e:
                    logger.warning(f"Failed to clear {item}: {e}")


def process_chapter(chapter_path: str, config_path: str = None) -> None:
    """
    Process a single chapter through the full engine.

    This is the top-level orchestration:
      1. Parse the chapter file into raw text (pipeline)
      2. Extract structured evidence (pipeline)
      3. Compute state delta (Narrative State Engine)
      4. Apply delta to current state
      5. Run editorial review over updated state
      6. Save everything
    """
    config = get_config(config_path)
    config.ensure_directories()

    # Load current narrative state
    state = load_narrative_state(config.memory_dir)

    chapter_file = Path(chapter_path)
    if not chapter_file.exists():
        logger.error(f"Chapter file not found: {chapter_path}")
        sys.exit(1)

    # Parse chapter number from filename if possible
    import re
    match = re.search(r'(?:chapter|ch|ch_)[^\d]*(\d+)', chapter_file.name, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
    else:
        chapter_num = state.last_processed_chapter + 1

    logger.info(f"Processing chapter: {chapter_file.name} (Resolved Chapter Number: {chapter_num})")
    logger.info(f"Current narrative state: {state.total_chapters_processed} chapters processed")

    # Read text to calculate hash
    try:
        with open(chapter_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        import hashlib
        text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        logger.info(f"Chapter file SHA-256: {text_hash}")
    except Exception as e:
        logger.warning(f"Could not calculate hash of chapter file: {e}")

    # === Phase 2+: Pipeline evidence extraction ===
    pipeline = Pipeline(config)
    chapter_data = pipeline.process_chapter(str(chapter_file), chapter_num=chapter_num, is_file=True, current_state=state)

    # === Phase 6+: Narrative State Engine ===
    engine = NarrativeStateEngine(config)
    delta = engine.process_chapter(chapter_data, state)
    state.apply_delta(delta)

    # === Phase 10+: Editorial Engine ===
    editorial = EditorialEngine(config)
    review = editorial.review(state, delta, raw_text=chapter_data.raw_text)

    # Persist updated state and report artifacts. narrative_state.json (canonical) first,
    # then the derived per-entity exports — never the other way around, since nothing should
    # be able to read a modular file that reflects a canonical write that didn't happen.
    save_narrative_state(state, config.memory_dir)
    save_modular_state(state, config)

    # Export narrative graph from updated state
    graph_builder = NarrativeGraph(config)
    graph_path = graph_builder.save(state, config.memory_dir)

    logger.info("Chapter processing complete.")
    logger.info(f"Applied delta: {delta.summary}")
    logger.info(f"Editorial report generated for chapter {chapter_num}")
    logger.info(f"Findings: {len(review.get('findings', []))}")
    logger.info(f"Narrative graph saved to {graph_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Narrative Intelligence Engine — Understand novels like a developmental editor."
    )
    parser.add_argument(
        "--chapter",
        type=str,
        help="Path to the chapter file to process (PDF, DOCX, or TXT).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration YAML file.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the current narrative state summary and exit.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Recursively purge all narrative databases, cache, and split chapters to start fresh.",
    )

    args = parser.parse_args()

    if args.clear:
        config = get_config(args.config)
        clear_subdirectories(config)
        print("Storage directories cleared successfully.")
        return

    if args.status:
        config = get_config(args.config)
        state = load_narrative_state(config.memory_dir)
        print(f"\n=== Narrative State Summary ===")
        print(f"Chapters processed: {state.total_chapters_processed}")
        print(f"Last chapter: {state.last_processed_chapter}")
        print(f"Characters tracked: {len(state.characters)}")
        print(f"Relationships tracked: {len(state.relationships)}")
        print(f"World elements: {len(state.world)}")
        print(f"Themes: {len(state.themes)}")
        print(f"Promises: {len(state.promises)}")
        print(f"Mysteries: {len(state.mysteries)}")
        print(f"Conflicts: {len(state.conflicts)}")
        print(f"Evidence pieces: {len(state.evidence_store)}")
        print(f"Timeline events: {len(state.timeline)}")
        print(f"================================\n")
        return

    if args.chapter:
        process_chapter(args.chapter, args.config)
    else:
        print("Narrative Intelligence Engine initialized.")
        print("Use --chapter <path> to process a chapter.")
        print("Use --status to see the current narrative state.")


if __name__ == "__main__":
    main()
