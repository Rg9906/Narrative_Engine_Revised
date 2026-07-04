from pathlib import Path
import json

from src.utils.config import get_config
from src.pipeline.pipeline import Pipeline
from src.models.state import NarrativeState
from src.engines.narrative_state import NarrativeStateEngine


def main():
    config = get_config()
    config.ensure_directories()

    pipeline = Pipeline(config)
    chapter_path = Path('tests') / 'data' / 'example_chapter.txt'
    print(f'Processing chapter: {chapter_path}')

    chapter_data = pipeline.process_chapter(str(chapter_path), chapter_num=1, is_file=True)

    state = NarrativeState()
    engine = NarrativeStateEngine(config)
    delta = engine.process_chapter(chapter_data, state)

    # Apply delta
    state.apply_delta(delta)

    # Save state
    memory_dir = config.memory_dir
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_path = memory_dir / 'narrative_state.json'
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

    # Print concise summary
    print('=== State Summary ===')
    print(f'Chapter processed: {state.last_processed_chapter}')
    print(f'Total chapters processed: {state.total_chapters_processed}')
    print(f'Characters tracked: {len(state.characters)}')
    print(f'Relationship entries: {len(state.relationships)}')
    print(f'World entries: {len(state.world)}')
    print(f'Timeline events: {len(state.timeline)}')
    print(f'Delta changes: {len(delta.changes)}')
    print(f'New evidence items: {len(delta.new_evidence)}')
    print(f'State saved to: {state_path}')


if __name__ == '__main__':
    main()
