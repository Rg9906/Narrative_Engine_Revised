"""Narrative graph builder (Phase 9).

Exports a simple JSON graph with `nodes` and `edges` derived from
`NarrativeState.characters` and `NarrativeState.relationships`.
"""

import json
from pathlib import Path
from typing import Any


class NarrativeGraph:
    def __init__(self, config: Any):
        self.config = config

    def build(self, state) -> dict:
        nodes = []
        edges = []

        def _entry_value(entry):
            if hasattr(entry, 'current') and entry.current is not None:
                return getattr(entry.current, 'value', None)
            if isinstance(entry, dict):
                return (entry.get('current') or {}).get('value')
            return None

        # Characters
        for cid, cdata in state.characters.items():
            name = _entry_value(cdata) or cid
            nodes.append({'id': f'char::{cid}', 'label': name, 'type': 'character'})

        # World elements
        for wid, wdata in state.world.items():
            label = _entry_value(wdata) or wid
            nodes.append({'id': f'world::{wid}', 'label': label, 'type': 'world'})

        # Themes and other elements
        for theme_id, theme_entry in getattr(state, 'themes', {}).items():
            value = _entry_value(theme_entry) or theme_id
            nodes.append({'id': f'theme::{theme_id}', 'label': value, 'type': 'theme'})

        # Relationships as edges between characters
        for rid, rdata in state.relationships.items():
            parts = rid.split('::')
            if len(parts) != 2:
                continue
            source, target = parts
            label = _entry_value(rdata) or 'UNKNOWN'
            edges.append({
                'id': rid,
                'source': f'char::{source}',
                'target': f'char::{target}',
                'label': label,
                'type': 'relationship',
            })

        # Timeline events as nodes and edges from chapter to event
        for idx, event in enumerate(getattr(state, 'timeline', []) or [], start=1):
            event_id = event.get('id') or f'evt::{idx}'
            desc = event.get('description') or 'timeline_event'
            nodes.append({'id': f'event::{event_id}', 'label': desc, 'type': 'event'})
            chapter_ref = event.get('chapter')
            if chapter_ref is not None:
                edges.append({
                    'id': f'evt_edge::{event_id}',
                    'source': f'event::{event_id}',
                    'target': f'chapter::{chapter_ref}',
                    'label': 'occurs_in',
                    'type': 'event_chapter',
                })

        # Chapter nodes for reference
        if getattr(state, 'total_chapters_processed', None) is not None:
            for chapter in range(1, state.total_chapters_processed + 1):
                nodes.append({'id': f'chapter::{chapter}', 'label': f'Chapter {chapter}', 'type': 'chapter'})

        return {'nodes': nodes, 'edges': edges}

    def save(self, state, out_path: Path | None = None) -> Path:
        out_path = Path(out_path or self.config.memory_dir) / 'narrative_graph.json'
        graph = self.build(state)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix('.json.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2, ensure_ascii=False)
        import os
        os.replace(tmp_path, out_path)
        return out_path
