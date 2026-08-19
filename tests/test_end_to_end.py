"""End-to-End integration tests for Narrative Intelligence Engine."""

import pytest
import shutil
import os
from pathlib import Path
from src.utils.config import Config
from src.pipeline.pipeline import Pipeline
from src.models.state import NarrativeState
from src.engines.narrative_state import NarrativeStateEngine
from src.engines.editorial_engine import EditorialEngine


@pytest.fixture
def temp_project_dir(tmp_path):
    # Setup temporary directory for test outputs
    data_dir = tmp_path / "data"
    memory_dir = data_dir / "memory"
    output_dir = data_dir / "output"
    
    # Create mock configuration overrides
    class MockConfig(Config):
        def __init__(self):
            super().__init__()
            self._config = {
                "paths": {
                    "data_dir": str(data_dir),
                    "memory_dir": str(memory_dir),
                    "output_dir": str(output_dir)
                },
                "pipeline": {
                    "spacy_model": "en_core_web_sm",
                    "entity_labels": ["person", "location", "object", "event"]
                }
            }
        
        @property
        def data_dir(self):
            return data_dir
            
        @property
        def memory_dir(self):
            return memory_dir
            
        @property
        def output_dir(self):
            return output_dir

    cfg = MockConfig()
    cfg.ensure_directories()
    return cfg


def test_full_pipeline_end_to_end(temp_project_dir):
    config = temp_project_dir
    
    # Source file path
    src_file = Path("tests") / "data" / "example_chapter.txt"
    assert src_file.exists(), "example_chapter.txt must exist under tests/data"
    
    # 1. Process chapter through sensory pipeline
    pipeline = Pipeline(config)
    chapter_data = pipeline.process_chapter(str(src_file), chapter_num=1, is_file=True)
    
    assert chapter_data.chapter_number == 1
    assert len(chapter_data.sentences) > 0
    assert len(chapter_data.paragraphs) > 0
    
    # 2. Ingest through NarrativeStateEngine
    state = NarrativeState()
    engine = NarrativeStateEngine(config)
    delta = engine.process_chapter(chapter_data, state)
    
    assert delta.chapter_number == 1
    assert len(delta.changes) > 0
    
    # Apply delta to state
    state.apply_delta(delta)
    assert state.last_processed_chapter == 1
    assert state.total_chapters_processed == 1
    
    # Verify memory states populated. The deterministic pass populates raw_relations
    # (dependency-parsed SVO triples); state.timeline is the CURATED chronology, which
    # is authored by the LLM timeline stage and so is legitimately empty here, since the
    # LLM provider is disabled under pytest.
    assert len(state.characters) > 0
    assert len(state.raw_relations) > 0
    assert len(state.themes) > 0
    
    # 3. Editorial Review
    editorial = EditorialEngine(config)
    report = editorial.review(state, delta)
    
    assert "findings" in report
    
    # Check that output files were generated
    state_file = config.memory_dir / "narrative_state.json"
    report_file = config.reports_dir / "editorial_report_ch1.json"
    graph_file = config.memory_dir / "narrative_graph.json"
    
    # Mock manual save since main.py usually does this
    import json
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2)

    # Export narrative graph
    from src.engines.narrative_graph import NarrativeGraph
    graph_builder = NarrativeGraph(config)
    graph_builder.save(state, config.memory_dir)
        
    assert state_file.exists()
    assert report_file.exists()
    assert graph_file.exists()
