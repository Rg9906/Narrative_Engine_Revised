"""Narrative graph builder (Phase 9).

Exports a simple JSON graph with `nodes` and `edges` derived from
`NarrativeState.characters` and `NarrativeState.relationships`.
"""

import json
from pathlib import Path
from typing import Any


def _entry_value(entry):
    """Read the current value off a single StateEntry (object or raw dict)."""
    if hasattr(entry, 'current') and entry.current is not None:
        return getattr(entry.current, 'value', None)
    if isinstance(entry, dict):
        return (entry.get('current') or {}).get('value')
    return None


def _field_chapters(entry) -> set:
    """Every chapter number a single StateEntry field was touched in
    (current value + full history), across StateEntry objects or the raw
    dict shape produced by JSON deserialization."""
    chapters: set = set()
    if entry is None:
        return chapters
    if hasattr(entry, 'get_trajectory'):
        for snap in entry.get_trajectory():
            ch = getattr(snap, 'chapter', None)
            if ch is not None:
                chapters.add(ch)
        return chapters
    if isinstance(entry, dict):
        current = entry.get('current') or {}
        if current.get('chapter') is not None:
            chapters.add(current['chapter'])
        for snap in entry.get('history') or []:
            if isinstance(snap, dict) and snap.get('chapter') is not None:
                chapters.add(snap['chapter'])
    return chapters


def _entity_label(entity_fields, candidate_field_keys, fallback_id: str) -> str:
    """Pick a human-readable label for a node.

    Bug fix: node labels used to be built by calling `_entry_value(entity_fields)`
    on the entity's whole *fields dict* (e.g. `{'canonical_name': StateEntry(...)}`)
    instead of on the specific field holding the display name. `_entry_value` only
    recognizes a single StateEntry (something with a `.current`/`current` key), so
    that call always fell through to `None` and every node silently displayed its
    raw snake_case ID instead of a readable name.
    """
    if isinstance(entity_fields, dict):
        for key in candidate_field_keys:
            value = _entry_value(entity_fields.get(key))
            if value:
                return str(value)
    return fallback_id


def _entity_active_chapters(entity_fields) -> set:
    """Union of active chapters across every field of one character/world/
    theme entity — i.e. every chapter this entity was mentioned or updated
    in, derived purely from already-persisted state (no new evidence
    plumbing needed)."""
    chapters: set = set()
    if not entity_fields:
        return chapters
    for field_entry in entity_fields.values():
        chapters |= _field_chapters(field_entry)
    return chapters


class NarrativeGraph:
    def __init__(self, config: Any):
        self.config = config

    def build(self, state) -> dict:
        nodes = []
        edges = []

        # Characters
        for cid, cdata in state.characters.items():
            name = _entity_label(cdata, ['canonical_name'], cid.replace('_', ' ').title())
            nodes.append({'id': f'char::{cid}', 'label': name, 'type': 'character'})

        # World elements — no dedicated name field in the current schema (see
        # WorldMemory), so a humanized ID is the fallback rather than the raw
        # snake_case ID; 'canonical_name'/'name' are checked in case an entry
        # was LLM-authored with one (ContextRetriever does the same lookup).
        for wid, wdata in state.world.items():
            label = _entity_label(wdata, ['canonical_name', 'name'], wid.replace('_', ' ').title())
            nodes.append({'id': f'world::{wid}', 'label': label, 'type': 'world'})

        # Themes and symbols (both live in state.themes, keyed by id prefix).
        for theme_id, theme_entry in getattr(state, 'themes', {}).items():
            value = _entity_label(theme_entry, ['theme_name', 'symbol_name'], theme_id.replace('_', ' ').title())
            nodes.append({'id': f'theme::{theme_id}', 'label': value, 'type': 'theme'})

        # Character <-> world edges: connect a character and a world element
        # whenever they were both active (mentioned/updated) in at least one
        # shared chapter. Derived purely from persisted StateEntry history —
        # no sentence-level evidence needed.
        char_chapters = {cid: _entity_active_chapters(cdata) for cid, cdata in state.characters.items()}
        world_chapters = {wid: _entity_active_chapters(wdata) for wid, wdata in state.world.items()}

        for cid, c_chs in char_chapters.items():
            if not c_chs:
                continue
            for wid, w_chs in world_chapters.items():
                shared = c_chs & w_chs
                if not shared:
                    continue
                edges.append({
                    'id': f'char_world::{cid}::{wid}',
                    'source': f'char::{cid}',
                    'target': f'world::{wid}',
                    'label': f"ch. {', '.join(str(c) for c in sorted(shared))}",
                    'type': 'character_world',
                })

        # Character <-> theme edges: connect a character to a theme/symbol
        # whenever the character was active in one of the chapters the theme
        # is already known to be present in (`chapters_present`, tracked by
        # ThemeMemory). Falls back to the theme entity's own active-chapter
        # union if `chapters_present` isn't populated for some reason.
        for theme_id, theme_fields in getattr(state, 'themes', {}).items():
            if not isinstance(theme_fields, dict):
                continue
            theme_chapters = set(_entry_value(theme_fields.get('chapters_present')) or [])
            if not theme_chapters:
                theme_chapters = _entity_active_chapters(theme_fields)
            if not theme_chapters:
                continue
            for cid, c_chs in char_chapters.items():
                shared = c_chs & theme_chapters
                if not shared:
                    continue
                edges.append({
                    'id': f'char_theme::{cid}::{theme_id}',
                    'source': f'char::{cid}',
                    'target': f'theme::{theme_id}',
                    'label': f"ch. {', '.join(str(c) for c in sorted(shared))}",
                    'type': 'character_theme',
                })

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
