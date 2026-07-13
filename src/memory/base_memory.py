"""
Base Memory — Foundation for all persistent narrative state modules.

Every memory module (Character, Relationship, World, Timeline, etc.)
inherits from BaseMemory
. It provides:

  - JSON serialization/deserialization
  - Versioned state with history preservation
  - Evidence-backed updates (never overwrite without provenance)
  - Dormancy tracking (what hasn't been mentioned recently)

The JSON files on disk are merely SERIALIZATION — they persist the state
between runs. The actual memory is the structured, interconnected,
versioned web of narrative understanding that lives in these objects.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.models.state import StateEntry, StateSnapshot, Evidence

logger = logging.getLogger("NarrativeEngine.Memory.Base")


class BaseMemory:
    """
    Base class for all narrative memory modules.

    Provides a common interface for:
      - Loading/saving state from/to JSON files
      - Managing StateEntry objects with full history
      - Tracking dormancy (elements not mentioned recently)

    Subclasses implement domain-specific update logic
    (e.g., how to update a character profile from evidence).
    """

    def __init__(self, memory_file: Optional[str] = None):
        """
        Args:
            memory_file: Path to the JSON file for persistence.
                         If None, operates in-memory only.
        """
        self._memory_file = Path(memory_file) if memory_file else None
        self._entries: Dict[str, Dict[str, StateEntry]] = {}
        self._metadata: Dict[str, Any] = {
            "version": 1,
            "last_updated_chapter": 0,
        }

    @property
    def entries(self) -> Dict[str, Dict[str, StateEntry]]:
        """Access the raw state entries."""
        return self._entries

    def get_entry(self, entity_id: str, field_key: str) -> Optional[StateEntry]:
        """Get a specific state entry for an entity."""
        entity = self._entries.get(entity_id)
        if entity:
            return entity.get(field_key)
        return None

    def set_entry(self, entity_id: str, field_key: str, entry: StateEntry) -> None:
        """Set a state entry for an entity."""
        if entity_id not in self._entries:
            self._entries[entity_id] = {}
        self._entries[entity_id][field_key] = entry

    def update_entry(
        self,
        entity_id: str,
        field_key: str,
        value: Any,
        chapter: int,
        scene: Optional[int] = None,
        evidence_ids: Optional[list] = None,
        confidence: float = 1.0,
        reasoning: str = "",
        importance: float = 0.5,
    ) -> StateEntry:
        """
        Update (or create) a state entry with a new snapshot.

        This is the primary way to modify state. It NEVER overwrites —
        it creates a new snapshot and preserves the old one in history.

        Returns:
            The updated StateEntry.
        """
        entry = self.get_entry(entity_id, field_key)

        if entry is None:
            # Create new entry
            entry = StateEntry(key=field_key, importance=importance)
            self.set_entry(entity_id, field_key, entry)

        # Create snapshot and update (preserving history)
        snapshot = StateSnapshot(
            value=value,
            chapter=chapter,
            scene=scene,
            evidence_ids=evidence_ids or [],
            confidence=confidence,
            reasoning=reasoning,
        )
        entry.update(snapshot)

        logger.debug(
            f"Updated {entity_id}.{field_key} → {value} "
            f"(ch{chapter}, conf={confidence:.2f}, v{entry.version})"
        )
        return entry

    def get_dormant_entries(self, current_chapter: int, threshold: int = 5) -> list:
        """
        Find state entries that haven't been mentioned in `threshold` chapters.

        Returns:
            List of (entity_id, field_key, StateEntry, chapters_dormant) tuples.
        """
        dormant = []
        for entity_id, fields in self._entries.items():
            for field_key, entry in fields.items():
                gap = entry.chapters_since_last_mention(current_chapter)
                if gap >= threshold:
                    dormant.append((entity_id, field_key, entry, gap))
        return dormant

    def list_entities(self) -> list:
        """List all entity IDs in this memory."""
        return list(self._entries.keys())

    def get_entity_state(self, entity_id: str) -> Optional[Dict[str, StateEntry]]:
        """Get all state entries for an entity."""
        return self._entries.get(entity_id)

    # --- Persistence ---

    def save(self, file_path: Optional[str] = None) -> None:
        """Save the memory state to a JSON file."""
        path = Path(file_path) if file_path else self._memory_file
        if path is None:
            logger.warning("No file path specified for saving memory")
            return

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "metadata": self._metadata,
            "entries": {
                entity_id: {
                    field_key: entry.to_dict()
                    for field_key, entry in fields.items()
                }
                for entity_id, fields in self._entries.items()
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Memory saved to {path} ({len(self._entries)} entities)")

    def load(self, file_path: Optional[Any] = None) -> None:
        """Load the memory state from a JSON file or from an in-memory dict."""
        data = None

        if isinstance(file_path, dict):
            data = file_path
        else:
            path = Path(file_path) if file_path else self._memory_file
            if path is None or not path.exists():
                logger.info("No existing memory file found, starting fresh")
                return

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

        if data is None:
            logger.info("No memory data provided, starting fresh")
            return

        self._metadata = data.get("metadata", self._metadata)

        raw_entries = data.get("entries") if isinstance(data, dict) and "entries" in data else data
        self._entries = {
            entity_id: {
                field_key: entry_data if isinstance(entry_data, StateEntry) else StateEntry.from_dict(entry_data)
                for field_key, entry_data in fields.items()
            }
            for entity_id, fields in raw_entries.items()
        }

        logger.info("Memory loaded from dict input" if isinstance(file_path, dict) else f"Memory loaded from {path} ({len(self._entries)} entities)")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entire memory to a dictionary."""
        return {
            "metadata": self._metadata,
            "entries": {
                eid: {fk: e.to_dict() for fk, e in fields.items()}
                for eid, fields in self._entries.items()
            },
        }
