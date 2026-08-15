"""Read-only access to the narrative graph export for the API layer."""

from __future__ import annotations

import json
from typing import Any

from src.utils.config import Config

EMPTY_GRAPH: dict[str, Any] = {"nodes": [], "edges": []}


def load_graph(config: Config) -> dict[str, Any]:
    path = config.memory_dir / "narrative_graph.json"
    if not path.exists():
        return json.loads(json.dumps(EMPTY_GRAPH))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
