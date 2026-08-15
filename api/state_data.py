"""Read-only access to the canonical narrative_state.json for the API layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.config import Config

# Collections that follow the generic `{id: {field_key: StateEntry}}` shape.
COLLECTION_KEYS = {
    "characters",
    "relationships",
    "world",
    "themes",
    "motifs",
    "promises",
    "threats",
    "mysteries",
    "conflicts",
    "arcs",
    "style",
}

EMPTY_STATE: dict[str, Any] = {
    "metadata": {
        "last_processed_chapter": 0,
        "total_chapters_processed": 0,
        "created_at": None,
        "last_updated": None,
    },
    **{key: {} for key in COLLECTION_KEYS},
    "timeline": [],
    "chapter_summaries": {},
    "evidence_store": {},
    "delta_history": [],
}


def state_path(config: Config) -> Path:
    return config.memory_dir / "narrative_state.json"


def load_raw_state(config: Config) -> dict[str, Any]:
    path = state_path(config)
    if not path.exists():
        return json.loads(json.dumps(EMPTY_STATE))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_summary(data: dict[str, Any]) -> dict[str, Any]:
    counts = {key: len(data.get(key, {}) or {}) for key in COLLECTION_KEYS}
    counts["timeline_events"] = len(data.get("timeline", []) or [])
    counts["evidence"] = len(data.get("evidence_store", {}) or {})

    timeline = data.get("timeline", []) or []
    recent_timeline = sorted(
        timeline, key=lambda e: e.get("chapter", 0) if isinstance(e, dict) else 0
    )[-8:][::-1]

    open_promises = 0
    for entry in (data.get("promises", {}) or {}).values():
        status = _current_value(entry, "status")
        if status and str(status).upper() == "OPEN":
            open_promises += 1

    unresolved_mysteries = 0
    for entry in (data.get("mysteries", {}) or {}).values():
        status = _current_value(entry, "status")
        if status and str(status).upper() not in {"RESOLVED", "FULFILLED", "CLOSED"}:
            unresolved_mysteries += 1

    return {
        "metadata": data.get("metadata", {}),
        "counts": counts,
        "open_promises": open_promises,
        "unresolved_mysteries": unresolved_mysteries,
        "recent_timeline": recent_timeline,
    }


def _current_value(entry: dict[str, Any], field_key: str) -> Any:
    field = (entry or {}).get(field_key)
    if not field:
        return None
    current = field.get("current")
    if not current:
        return None
    return current.get("value")


def list_entities(data: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    raw = data.get(collection, {}) or {}
    return [{"id": entity_id, "fields": fields} for entity_id, fields in raw.items()]


def get_entity(data: dict[str, Any], collection: str, entity_id: str) -> dict[str, Any] | None:
    raw = data.get(collection, {}) or {}
    fields = raw.get(entity_id)
    if fields is None:
        return None
    return {"id": entity_id, "fields": fields}


def get_evidence(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("evidence_store", {}) or {}
