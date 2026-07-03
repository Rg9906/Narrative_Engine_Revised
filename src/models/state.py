"""
Core data models for the Narrative Intelligence Engine.

These models define the fundamental data structures that flow through the entire
system. They represent the distinction between:

  - EVIDENCE: Raw observations extracted by the NLP pipeline (what was seen in text)
  - STATE: Interpreted narrative understanding (what the engine believes to be true)
  - DELTA: What changed after processing a chapter (state transitions)

Nothing here is a simple key-value store. Every piece of state carries:
  - History (how it evolved)
  - Evidence (what supports it)
  - Confidence (how sure we are)
  - Source (where it came from)
  - Reasoning (why we believe it)

This emulates how a human developmental editor remembers a novel — not as
disconnected facts, but as an evolving web of understanding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


# =============================================================================
# ENUMS — Categorizing types of evidence and state
# =============================================================================

class EvidenceType(Enum):
    """How a piece of evidence was obtained from the text."""
    DIRECT_STATEMENT = auto()     # Narration directly states it ("Alice had blue eyes")
    DIALOGUE = auto()             # A character says it ("I'm afraid of water")
    ACTION = auto()               # Inferred from action ("She ran" → she can run)
    DESCRIPTION = auto()          # Descriptive passage ("The castle loomed")
    INFERENCE = auto()            # Derived by reasoning, not directly stated
    INTERNAL_THOUGHT = auto()     # Character's inner monologue
    AUTHORIAL_VOICE = auto()      # Narrator commentary outside character perspective


class ConfidenceLevel(Enum):
    """How confident the engine is in a piece of state."""
    CERTAIN = auto()        # Directly and unambiguously stated
    HIGH = auto()           # Strong evidence, minor interpretation needed
    MODERATE = auto()       # Reasonable inference from available evidence
    LOW = auto()            # Weak evidence or significant interpretation
    SPECULATIVE = auto()    # Educated guess based on patterns


class StateChangeType(Enum):
    """What kind of change a delta represents."""
    INTRODUCTION = auto()    # Something new appears for the first time
    EVOLUTION = auto()       # An existing state transitions to a new value
    CONFIRMATION = auto()    # Existing state is reinforced (confidence boost)
    CONTRADICTION = auto()   # New evidence conflicts with existing state
    RESOLUTION = auto()      # A question/promise/conflict is resolved
    DORMANCY = auto()        # Something hasn't been mentioned in a while


class RelationshipType(Enum):
    """Categories of character relationships."""
    FAMILY = auto()
    ROMANTIC = auto()
    FRIENDSHIP = auto()
    RIVALRY = auto()
    MENTORSHIP = auto()
    ALLIANCE = auto()
    ENMITY = auto()
    PROFESSIONAL = auto()
    UNKNOWN = auto()


class NarrativeElementType(Enum):
    """Types of narrative elements tracked in the graph."""
    CHARACTER = auto()
    LOCATION = auto()
    OBJECT = auto()
    EVENT = auto()
    THEME = auto()
    PROMISE = auto()
    CONFLICT = auto()
    MYSTERY = auto()
    SCENE = auto()
    ARC = auto()


# =============================================================================
# EVIDENCE — What the NLP pipeline extracts (raw observations)
# =============================================================================

@dataclass
class TextSpan:
    """A precise location in the source text."""
    text: str                        # The actual text content
    start_char: int                  # Character offset start
    end_char: int                    # Character offset end
    sentence_index: Optional[int] = None  # Which sentence in the chapter


@dataclass
class Evidence:
    """
    A single piece of evidence extracted from text.

    Evidence is NOT understanding. It is raw material that the Narrative State
    Engine will interpret, contextualize, and integrate into the evolving state.

    Example:
        text_span: "She watched the door long after it closed"
        evidence_type: DESCRIPTION
        source_chapter: 3
        source_scene: 2
        confidence: 0.85
        related_entities: ["Alice"]
        interpretation_hint: "Suggests emotional attachment or sadness"
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    text_span: Optional[TextSpan] = None
    evidence_type: EvidenceType = EvidenceType.DIRECT_STATEMENT
    source_chapter: int = 0
    source_scene: Optional[int] = None
    confidence: float = 1.0
    related_entities: List[str] = field(default_factory=list)
    interpretation_hint: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "id": self.id,
            "text_span": {
                "text": self.text_span.text,
                "start_char": self.text_span.start_char,
                "end_char": self.text_span.end_char,
                "sentence_index": self.text_span.sentence_index,
            } if self.text_span else None,
            "evidence_type": self.evidence_type.name,
            "source_chapter": self.source_chapter,
            "source_scene": self.source_scene,
            "confidence": self.confidence,
            "related_entities": self.related_entities,
            "interpretation_hint": self.interpretation_hint,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        """Deserialize from dictionary."""
        text_span = None
        if data.get("text_span"):
            ts = data["text_span"]
            text_span = TextSpan(
                text=ts["text"],
                start_char=ts["start_char"],
                end_char=ts["end_char"],
                sentence_index=ts.get("sentence_index"),
            )
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            text_span=text_span,
            evidence_type=EvidenceType[data.get("evidence_type", "DIRECT_STATEMENT")],
            source_chapter=data.get("source_chapter", 0),
            source_scene=data.get("source_scene"),
            confidence=data.get("confidence", 1.0),
            related_entities=data.get("related_entities", []),
            interpretation_hint=data.get("interpretation_hint", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


# =============================================================================
# STATE ENTRIES — What the engine believes to be true (with full provenance)
# =============================================================================

@dataclass
class StateSnapshot:
    """
    A single historical snapshot of a state value at a given point in time.

    This allows the engine to remember not just what IS true, but what WAS true
    and when/why it changed.
    """
    value: Any                       # The state value at this point
    chapter: int                     # When this value was established
    scene: Optional[int] = None      # Specific scene within chapter
    evidence_ids: List[str] = field(default_factory=list)  # Evidence supporting this
    confidence: float = 1.0
    reasoning: str = ""              # Why the engine believes this
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "chapter": self.chapter,
            "scene": self.scene,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateSnapshot":
        return cls(
            value=data["value"],
            chapter=data["chapter"],
            scene=data.get("scene"),
            evidence_ids=data.get("evidence_ids", []),
            confidence=data.get("confidence", 1.0),
            reasoning=data.get("reasoning", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class StateEntry:
    """
    A single piece of narrative state — the engine's current belief about
    something, along with its full evolution history.

    This is NOT a simple key-value pair. It is a versioned, evidenced,
    historically-aware belief.

    Example (Alice's emotional state):
        key: "emotional_state"
        current: StateSnapshot(value="sad", chapter=3, evidence=[...])
        history: [
            StateSnapshot(value="optimistic", chapter=1, ...),
            StateSnapshot(value="cautiously_hopeful", chapter=2, ...),
        ]
        importance: 0.8
        dependencies: ["alice_brother_departure"]  # linked to another state entry
    """
    key: str                         # What this state represents
    current: Optional[StateSnapshot] = None   # Current believed value
    history: List[StateSnapshot] = field(default_factory=list)  # All previous values
    importance: float = 0.5          # How narratively important (0-1)
    dependencies: List[str] = field(default_factory=list)   # IDs of related state
    element_type: NarrativeElementType = NarrativeElementType.CHARACTER
    version: int = 1                 # Incremented on each update
    last_mentioned_chapter: int = 0  # For dormancy tracking

    def update(self, new_snapshot: StateSnapshot) -> None:
        """
        Transition to a new state value, preserving the old one in history.
        Never overwrites — always preserves the evolution.
        """
        if self.current is not None:
            self.history.append(self.current)
        self.current = new_snapshot
        self.version += 1
        self.last_mentioned_chapter = new_snapshot.chapter

    def get_trajectory(self) -> List[StateSnapshot]:
        """Return the full evolution: history + current, in chronological order."""
        trajectory = list(self.history)
        if self.current is not None:
            trajectory.append(self.current)
        return trajectory

    def chapters_since_last_mention(self, current_chapter: int) -> int:
        """How many chapters since this state was last referenced."""
        return current_chapter - self.last_mentioned_chapter

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "current": self.current.to_dict() if self.current else None,
            "history": [s.to_dict() for s in self.history],
            "importance": self.importance,
            "dependencies": self.dependencies,
            "element_type": self.element_type.name,
            "version": self.version,
            "last_mentioned_chapter": self.last_mentioned_chapter,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateEntry":
        current = None
        if data.get("current"):
            current = StateSnapshot.from_dict(data["current"])
        history = [StateSnapshot.from_dict(s) for s in data.get("history", [])]
        return cls(
            key=data["key"],
            current=current,
            history=history,
            importance=data.get("importance", 0.5),
            dependencies=data.get("dependencies", []),
            element_type=NarrativeElementType[data.get("element_type", "CHARACTER")],
            version=data.get("version", 1),
            last_mentioned_chapter=data.get("last_mentioned_chapter", 0),
        )


# =============================================================================
# CHAPTER DATA — Structured evidence output from the NLP pipeline
# =============================================================================

@dataclass
class ExtractedEntity:
    """An entity extracted by the NLP pipeline (evidence, not state)."""
    text: str                        # Entity surface text
    label: str                       # Entity type (person, location, etc.)
    span: Optional[TextSpan] = None  # Location in text
    confidence: float = 1.0
    coreference_cluster: Optional[int] = None  # Which coref cluster it belongs to


@dataclass
class ExtractedRelation:
    """A relation extracted by dependency/event parsing (evidence, not state)."""
    subject: str
    predicate: str
    object: str
    span: Optional[TextSpan] = None
    confidence: float = 1.0


@dataclass
class ExtractedDialogue:
    """A dialogue utterance with attributed speaker (evidence, not state)."""
    speaker: str                     # Attributed speaker (or "Unknown")
    text: str                        # The spoken text
    span: Optional[TextSpan] = None
    confidence: float = 1.0          # Confidence in speaker attribution


@dataclass
class ChapterData:
    """
    The structured output of the NLP pipeline for one chapter.

    This is EVIDENCE — raw observations extracted from text. It is NOT
    narrative understanding. The Narrative State Engine will interpret this
    evidence and produce state transitions.

    Think of this as "what the eyes saw" — not "what the mind understood."
    """
    chapter_number: int
    raw_text: str = ""
    sentences: List[str] = field(default_factory=list)
    entities: List[ExtractedEntity] = field(default_factory=list)
    coreference_clusters: List[List[str]] = field(default_factory=list)
    relations: List[ExtractedRelation] = field(default_factory=list)
    dialogues: List[ExtractedDialogue] = field(default_factory=list)
    scenes: List[Dict[str, Any]] = field(default_factory=list)

    # Style metrics (evidence about HOW the text is written)
    style_metrics: Dict[str, Any] = field(default_factory=dict)

    # Raw spaCy doc tokens if needed for deeper analysis
    # (not serialized — ephemeral)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "sentence_count": len(self.sentences),
            "entity_count": len(self.entities),
            "entities": [
                {"text": e.text, "label": e.label, "confidence": e.confidence}
                for e in self.entities
            ],
            "coreference_clusters": self.coreference_clusters,
            "relations": [
                {"subject": r.subject, "predicate": r.predicate, "object": r.object}
                for r in self.relations
            ],
            "dialogues": [
                {"speaker": d.speaker, "text": d.text}
                for d in self.dialogues
            ],
            "scene_count": len(self.scenes),
            "style_metrics": self.style_metrics,
        }


# =============================================================================
# STATE DELTA — What changed after processing a chapter
# =============================================================================

@dataclass
class StateChange:
    """
    A single change to the narrative state produced by processing a chapter.

    Each change records WHAT changed, HOW it changed, and WHY.
    """
    change_type: StateChangeType
    target_type: NarrativeElementType  # What kind of element changed
    target_id: str                     # ID of the element that changed
    field_key: str                     # Which field/attribute changed
    old_value: Any = None              # Previous value (None if INTRODUCTION)
    new_value: Any = None              # New value
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 1.0
    reasoning: str = ""                # Why this change was made

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_type": self.change_type.name,
            "target_type": self.target_type.name,
            "target_id": self.target_id,
            "field_key": self.field_key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class StateDelta:
    """
    The complete set of changes produced by processing one chapter.

    This is the bridge between evidence and state. The Narrative State Engine
    produces a delta; the delta is then applied to the current state.

    State(n) = State(n-1) + Delta(chapter_n)
    """
    chapter_number: int
    changes: List[StateChange] = field(default_factory=list)
    new_evidence: List[Evidence] = field(default_factory=list)
    summary: str = ""                  # Human-readable summary of what changed
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def introductions(self) -> List[StateChange]:
        """New elements introduced in this chapter."""
        return [c for c in self.changes if c.change_type == StateChangeType.INTRODUCTION]

    @property
    def evolutions(self) -> List[StateChange]:
        """Existing elements that evolved."""
        return [c for c in self.changes if c.change_type == StateChangeType.EVOLUTION]

    @property
    def contradictions(self) -> List[StateChange]:
        """Evidence that contradicts existing state."""
        return [c for c in self.changes if c.change_type == StateChangeType.CONTRADICTION]

    @property
    def confirmations(self) -> List[StateChange]:
        """Evidence that confirms/reinforces existing state."""
        return [c for c in self.changes if c.change_type == StateChangeType.CONFIRMATION]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "change_count": len(self.changes),
            "changes": [c.to_dict() for c in self.changes],
            "new_evidence_count": len(self.new_evidence),
            "new_evidence": [e.to_dict() for e in self.new_evidence],
            "summary": self.summary,
            "timestamp": self.timestamp,
        }


# =============================================================================
# NARRATIVE STATE — The complete evolving understanding of the novel
# =============================================================================

@dataclass
class NarrativeState:
    """
    The top-level container for ALL evolving narrative state.

    This IS the engine's understanding of the novel at any point in time.
    It is not a database — it is a living, interconnected, versioned model
    of everything the engine believes about the story.

    The JSON serialization is merely persistence. This object IS the memory.
    """
    # Metadata
    last_processed_chapter: int = 0
    total_chapters_processed: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    # Character states (keyed by character ID)
    characters: Dict[str, Dict[str, StateEntry]] = field(default_factory=dict)

    # Relationship states (keyed by "char1_id::char2_id")
    relationships: Dict[str, Dict[str, StateEntry]] = field(default_factory=dict)

    # World state (locations, objects, rules)
    world: Dict[str, Dict[str, StateEntry]] = field(default_factory=dict)

    # Timeline (ordered list of events)
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    # Themes and symbols
    themes: Dict[str, StateEntry] = field(default_factory=dict)

    # Promises, foreshadowing, mysteries (keyed by unique ID)
    promises: Dict[str, StateEntry] = field(default_factory=dict)
    mysteries: Dict[str, StateEntry] = field(default_factory=dict)

    # Conflicts and arcs
    conflicts: Dict[str, StateEntry] = field(default_factory=dict)
    arcs: Dict[str, StateEntry] = field(default_factory=dict)

    # Style and voice observations
    style: Dict[str, StateEntry] = field(default_factory=dict)

    # All evidence collected (keyed by evidence ID)
    evidence_store: Dict[str, Evidence] = field(default_factory=dict)

    # History of all deltas applied (one per chapter)
    delta_history: List[StateDelta] = field(default_factory=list)

    def add_evidence(self, evidence: Evidence) -> None:
        """Store a piece of evidence in the global evidence store."""
        self.evidence_store[evidence.id] = evidence

    def apply_delta(self, delta: StateDelta) -> None:
        """
        Apply a chapter delta to the narrative state.
        This is the fundamental state transition operation.
        """
        for evidence in delta.new_evidence:
            self.add_evidence(evidence)

        self.delta_history.append(delta)
        self.last_processed_chapter = delta.chapter_number
        self.total_chapters_processed += 1
        self.last_updated = datetime.now().isoformat()

    def get_character(self, char_id: str) -> Optional[Dict[str, StateEntry]]:
        """Get all state entries for a character."""
        return self.characters.get(char_id)

    def get_relationship(self, char1_id: str, char2_id: str) -> Optional[Dict[str, StateEntry]]:
        """Get relationship state between two characters (order-independent)."""
        key1 = f"{char1_id}::{char2_id}"
        key2 = f"{char2_id}::{char1_id}"
        return self.relationships.get(key1) or self.relationships.get(key2)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire narrative state for JSON persistence."""

        def _serialize_state_dict(d: Dict[str, Dict[str, StateEntry]]) -> Dict:
            return {
                k: {sk: sv.to_dict() for sk, sv in v.items()}
                for k, v in d.items()
            }

        def _serialize_flat_state_dict(d: Dict[str, StateEntry]) -> Dict:
            return {k: v.to_dict() for k, v in d.items()}

        return {
            "metadata": {
                "last_processed_chapter": self.last_processed_chapter,
                "total_chapters_processed": self.total_chapters_processed,
                "created_at": self.created_at,
                "last_updated": self.last_updated,
            },
            "characters": _serialize_state_dict(self.characters),
            "relationships": _serialize_state_dict(self.relationships),
            "world": _serialize_state_dict(self.world),
            "timeline": self.timeline,
            "themes": _serialize_flat_state_dict(self.themes),
            "promises": _serialize_flat_state_dict(self.promises),
            "mysteries": _serialize_flat_state_dict(self.mysteries),
            "conflicts": _serialize_flat_state_dict(self.conflicts),
            "arcs": _serialize_flat_state_dict(self.arcs),
            "style": _serialize_flat_state_dict(self.style),
            "evidence_store": {k: v.to_dict() for k, v in self.evidence_store.items()},
            "delta_history": [d.to_dict() for d in self.delta_history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeState":
        """Deserialize from a dictionary (loaded from JSON)."""

        def _deserialize_state_dict(d: Dict) -> Dict[str, Dict[str, StateEntry]]:
            return {
                k: {sk: StateEntry.from_dict(sv) for sk, sv in v.items()}
                for k, v in d.items()
            }

        def _deserialize_flat_state_dict(d: Dict) -> Dict[str, StateEntry]:
            return {k: StateEntry.from_dict(v) for k, v in d.items()}

        metadata = data.get("metadata", {})

        state = cls(
            last_processed_chapter=metadata.get("last_processed_chapter", 0),
            total_chapters_processed=metadata.get("total_chapters_processed", 0),
            created_at=metadata.get("created_at", datetime.now().isoformat()),
            last_updated=metadata.get("last_updated", datetime.now().isoformat()),
        )

        state.characters = _deserialize_state_dict(data.get("characters", {}))
        state.relationships = _deserialize_state_dict(data.get("relationships", {}))
        state.world = _deserialize_state_dict(data.get("world", {}))
        state.timeline = data.get("timeline", [])
        state.themes = _deserialize_flat_state_dict(data.get("themes", {}))
        state.promises = _deserialize_flat_state_dict(data.get("promises", {}))
        state.mysteries = _deserialize_flat_state_dict(data.get("mysteries", {}))
        state.conflicts = _deserialize_flat_state_dict(data.get("conflicts", {}))
        state.arcs = _deserialize_flat_state_dict(data.get("arcs", {}))
        state.style = _deserialize_flat_state_dict(data.get("style", {}))

        # Deserialize evidence store
        for eid, edata in data.get("evidence_store", {}).items():
            state.evidence_store[eid] = Evidence.from_dict(edata)

        return state
