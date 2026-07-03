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

from src.models.state import NarrativeState
from src.utils.config import get_config


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
    """Persist the narrative state to disk."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_path = memory_dir / "narrative_state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info(f"Narrative state saved to {state_path}")


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

    logger.info(f"Processing chapter: {chapter_file.name}")
    logger.info(f"Current narrative state: {state.total_chapters_processed} chapters processed")

    # === Phase 2+: Pipeline evidence extraction ===
    # TODO: Implement pipeline integration
    # from src.pipeline.pipeline import Pipeline
    # pipeline = Pipeline(config)
    # chapter_data = pipeline.process_chapter(chapter_path)

    # === Phase 6+: Narrative State Engine ===
    # TODO: Implement state engine integration
    # from src.engines.narrative_state import NarrativeStateEngine
    # engine = NarrativeStateEngine(config)
    # delta = engine.process_chapter(chapter_data, state)
    # state.apply_delta(delta)

    # === Phase 10+: Editorial Engine ===
    # TODO: Implement editorial engine integration
    # from src.engines.editorial_engine import EditorialEngine
    # editorial = EditorialEngine(config)
    # review = editorial.review(state, delta)

    # Save updated state
    save_narrative_state(state, config.memory_dir)

    logger.info("Chapter processing complete.")


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

    args = parser.parse_args()

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
