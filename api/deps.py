"""Shared config/state access for the API layer.

Read endpoints deliberately parse narrative_state.json straight off disk rather than
reconstructing a full NarrativeState dataclass — the on-disk shape already matches what
the frontend needs, and it keeps read endpoints free of the heavy NLP imports (spaCy /
GLiNER / FastCoref) that the ingestion path requires. Those are imported lazily inside
the ingestion job instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.config import get_config, Config  # noqa: E402

_config: Config | None = None


def get_project_config() -> Config:
    global _config
    if _config is None:
        _config = get_config()
        _config.ensure_directories()
    return _config
