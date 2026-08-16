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
from typing import Any, Dict, List, Optional, Tuple


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
    THREAT = auto()
    CONFLICT = auto()
    MYSTERY = auto()
    SCENE = auto()
    ARC = auto()
    STYLE = auto()
    MOTIF = auto()


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "sentence_index": self.sentence_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextSpan":
        return cls(
            text=data["text"],
            start_char=data["start_char"],
            end_char=data["end_char"],
            sentence_index=data.get("sentence_index"),
        )


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
            "text_span": self.text_span.to_dict() if self.text_span else None,
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
            text_span = TextSpan.from_dict(data["text_span"])
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
    normalized_text: str = ""
    source: str = "unknown"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedEntity:
        span_data = data.get("span")
        span = TextSpan.from_dict(span_data) if span_data else None
        return cls(
            text=data["text"],
            label=data["label"],
            span=span,
            confidence=data.get("confidence", 1.0),
            coreference_cluster=data.get("coreference_cluster"),
            normalized_text=data.get("normalized_text", ""),
            source=data.get("source", "unknown"),
        )


@dataclass
class ExtractedCoreferenceCluster:
    """A group of mentions that refer to the same narrative entity."""
    mentions: List[str]
    # Character-offset (start, end) span for each entry in `mentions`, same order —
    # FastCoref's CorefResult.get_clusters(as_strings=False) already computes these
    # precisely; carrying them through lets consumers (e.g. CharacterMemory) determine
    # which sentence/paragraph a given mention actually falls in, rather than only
    # having the resolved text with no positional information.
    mention_spans: List[Tuple[Optional[int], Optional[int]]] = field(default_factory=list)
    canonical_mention: str = ""
    confidence: float = 1.0
    cluster_id: Optional[int] = None
    source: str = "unknown"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedCoreferenceCluster:
        return cls(
            mentions=data["mentions"],
            mention_spans=[tuple(s) for s in data.get("mention_spans", [])],
            canonical_mention=data.get("canonical_mention", ""),
            confidence=data.get("confidence", 1.0),
            cluster_id=data.get("cluster_id"),
            source=data.get("source", "unknown"),
        )


@dataclass
class ExtractedRelation:
    """A relation extracted by dependency/event parsing (evidence, not state)."""
    subject: str
    predicate: str
    object: str
    span: Optional[TextSpan] = None
    confidence: float = 1.0
    source: str = "unknown"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedRelation:
        span_data = data.get("span")
        span = TextSpan.from_dict(span_data) if span_data else None
        return cls(
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            span=span,
            confidence=data.get("confidence", 1.0),
            source=data.get("source", "unknown"),
        )


@dataclass
class ExtractedDialogue:
    """A dialogue utterance with attributed speaker (evidence, not state)."""
    speaker: str                     # Attributed speaker (or "Unknown")
    text: str                        # The spoken text
    span: Optional[TextSpan] = None
    confidence: float = 1.0          # Confidence in speaker attribution
    attribution_method: str = "unknown"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedDialogue:
        span_data = data.get("span")
        span = TextSpan.from_dict(span_data) if span_data else None
        return cls(
            speaker=data["speaker"],
            text=data["text"],
            span=span,
            confidence=data.get("confidence", 1.0),
            attribution_method=data.get("attribution_method", "unknown"),
        )


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
    source_name: str = ""
    chapter_title: str = ""
    raw_text: str = ""
    paragraphs: List[str] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    # Character-offset span for each entry in `sentences`, same sentence_index —
    # computed once by Pipeline._sentence_spans and persisted here so downstream
    # consumers (e.g. CharacterMemory) can determine which sentence a coreference
    # mention span falls into, without re-deriving sentence positions themselves.
    sentence_spans: List["TextSpan"] = field(default_factory=list)
    entities: List[ExtractedEntity] = field(default_factory=list)
    coreference_clusters: List[List[str]] = field(default_factory=list)
    coreferences: List[ExtractedCoreferenceCluster] = field(default_factory=list)
    relations: List[ExtractedRelation] = field(default_factory=list)
    dialogues: List[ExtractedDialogue] = field(default_factory=list)
    scenes: List[Dict[str, Any]] = field(default_factory=list)

    # Style metrics (evidence about HOW the text is written)
    style_metrics: Dict[str, Any] = field(default_factory=dict)
    validation_warnings: List[str] = field(default_factory=list)
    extraction_notes: List[str] = field(default_factory=list)

    # Raw spaCy doc tokens if needed for deeper analysis
    # (not serialized — ephemeral)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "source_name": self.source_name,
            "chapter_title": self.chapter_title,
            "raw_text": self.raw_text,
            "paragraph_count": len(self.paragraphs),
            "paragraphs": self.paragraphs,
            "sentence_count": len(self.sentences),
            "sentences": self.sentences,
            "sentence_spans": [s.to_dict() for s in self.sentence_spans],
            "entity_count": len(self.entities),
            "entities": [
                {
                    "text": e.text,
                    "label": e.label,
                    "normalized_text": e.normalized_text,
                    "confidence": e.confidence,
                    "span": e.span.to_dict() if e.span else None,
                    "coreference_cluster": e.coreference_cluster,
                    "source": e.source,
                }
                for e in self.entities
            ],
            "coreference_clusters": self.coreference_clusters,
            "coreferences": [
                {
                    "mentions": c.mentions,
                    "mention_spans": [list(s) for s in c.mention_spans],
                    "canonical_mention": c.canonical_mention,
                    "confidence": c.confidence,
                    "cluster_id": c.cluster_id,
                    "source": c.source,
                }
                for c in self.coreferences
            ],
            "relations": [
                {
                    "subject": r.subject,
                    "predicate": r.predicate,
                    "object": r.object,
                    "span": r.span.to_dict() if r.span else None,
                    "confidence": r.confidence,
                    "source": r.source,
                }
                for r in self.relations
            ],
            "dialogues": [
                {
                    "speaker": d.speaker,
                    "text": d.text,
                    "span": d.span.to_dict() if d.span else None,
                    "confidence": d.confidence,
                    "attribution_method": d.attribution_method,
                }
                for d in self.dialogues
            ],
            "scene_count": len(self.scenes),
            "scenes": self.scenes,
            "style_metrics": self.style_metrics,
            "validation_warnings": self.validation_warnings,
            "extraction_notes": self.extraction_notes,
            "evidence_summary": self.evidence_summary(),
        }

    def validate(self) -> List[str]:
        """Return warnings about incomplete or inconsistent chapter evidence."""
        warnings = []
        # Chapters may be 0-indexed (this project's own convention --
        # chapter_00_prologue.txt is a real, valid chapter 0). Confirmed
        # this false positive was already present in the real, committed
        # data/cache/chapter_0_*.json before this fix. Caught by a
        # self-review pass.
        if self.chapter_number < 0:
            warnings.append("chapter_number should be >= 0")
        if not self.raw_text.strip():
            warnings.append("raw_text is empty")
        if self.raw_text and not self.sentences:
            warnings.append("raw_text is present but no sentences were extracted")
        if self.raw_text and not self.paragraphs:
            warnings.append("raw_text is present but no paragraphs were extracted")

        for entity in self.entities:
            if not entity.text.strip():
                warnings.append("entity has empty text")
            if not entity.label.strip():
                warnings.append(f"entity '{entity.text}' has empty label")

        for relation in self.relations:
            if not relation.subject or not relation.predicate or not relation.object:
                warnings.append("relation is missing subject, predicate, or object")

        for dialogue in self.dialogues:
            if not dialogue.text.strip():
                warnings.append("dialogue has empty text")

        self.validation_warnings = warnings
        return warnings

    def evidence_summary(self) -> Dict[str, int]:
        """Compact count summary for downstream engines and diagnostics."""
        return {
            "paragraphs": len(self.paragraphs),
            "sentences": len(self.sentences),
            "entities": len(self.entities),
            "coreference_clusters": len(self.coreferences),
            "relations": len(self.relations),
            "dialogues": len(self.dialogues),
            "scenes": len(self.scenes),
            "validation_warnings": len(self.validation_warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChapterData:
        entities = [ExtractedEntity.from_dict(e) for e in data.get("entities", [])]
        coreferences = [ExtractedCoreferenceCluster.from_dict(c) for c in data.get("coreferences", [])]
        relations = [ExtractedRelation.from_dict(r) for r in data.get("relations", [])]
        dialogues = [ExtractedDialogue.from_dict(d) for d in data.get("dialogues", [])]
        sentence_spans = [TextSpan.from_dict(s) for s in data.get("sentence_spans", [])]
        return cls(
            chapter_number=data["chapter_number"],
            source_name=data.get("source_name", ""),
            chapter_title=data.get("chapter_title", ""),
            raw_text=data.get("raw_text", ""),
            paragraphs=data.get("paragraphs", []),
            sentences=data.get("sentences", []),
            sentence_spans=sentence_spans,
            entities=entities,
            coreference_clusters=data.get("coreference_clusters", []),
            coreferences=coreferences,
            relations=relations,
            dialogues=dialogues,
            scenes=data.get("scenes", []),
            style_metrics=data.get("style_metrics", {}),
            validation_warnings=data.get("validation_warnings", []),
            extraction_notes=data.get("extraction_notes", []),
        )


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

    # Contextual lookback: the tail of the most recently processed chapter's raw
    # text, carried alongside the structured state so the next chapter's LLM
    # extraction stages have direct continuity (e.g. a scene spanning a chapter
    # break) that structured fields alone wouldn't capture. Set once per chapter
    # in src/main.py, after that chapter's delta has been applied — so when
    # ContextRetriever reads it during THIS chapter's processing, it still holds
    # the PREVIOUS chapter's tail, not the current one.
    previous_chapter_excerpt: str = ""
    previous_chapter_number: Optional[int] = None

    # Character states (keyed by character ID)
    characters: Dict[str, Dict[str, StateEntry]] = field(default_factory=dict)

    # Relationship states (keyed by "char1_id::char2_id")
    relationships: Dict[str, Dict[str, StateEntry]] = field(default_factory=dict)

    # World state (locations, objects, rules)
    world: Dict[str, Dict[str, StateEntry]] = field(default_factory=dict)

    # Timeline (ordered list of events)
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    # Themes and motifs
    themes: Dict[str, StateEntry] = field(default_factory=dict)
    motifs: Dict[str, StateEntry] = field(default_factory=dict)

    # Promises, threats, foreshadowing, mysteries (keyed by unique ID)
    promises: Dict[str, StateEntry] = field(default_factory=dict)
    threats: Dict[str, StateEntry] = field(default_factory=dict)
    mysteries: Dict[str, StateEntry] = field(default_factory=dict)

    # Chapter summaries
    chapter_summaries: Dict[int, str] = field(default_factory=dict)

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

        return {
            "metadata": {
                "last_processed_chapter": self.last_processed_chapter,
                "total_chapters_processed": self.total_chapters_processed,
                "created_at": self.created_at,
                "last_updated": self.last_updated,
                "previous_chapter_excerpt": self.previous_chapter_excerpt,
                "previous_chapter_number": self.previous_chapter_number,
            },
            "characters": _serialize_state_dict(self.characters),
            "relationships": _serialize_state_dict(self.relationships),
            "world": _serialize_state_dict(self.world),
            "timeline": self.timeline,
            "themes": _serialize_state_dict(self.themes),
            "motifs": _serialize_state_dict(self.motifs),
            "promises": _serialize_state_dict(self.promises),
            "threats": _serialize_state_dict(self.threats),
            "mysteries": _serialize_state_dict(self.mysteries),
            "chapter_summaries": self.chapter_summaries,
            "conflicts": _serialize_state_dict(self.conflicts),
            "arcs": _serialize_state_dict(self.arcs),
            "style": _serialize_state_dict(self.style),
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
            previous_chapter_excerpt=metadata.get("previous_chapter_excerpt", ""),
            previous_chapter_number=metadata.get("previous_chapter_number"),
        )

        state.characters = _deserialize_state_dict(data.get("characters", {}))
        state.relationships = _deserialize_state_dict(data.get("relationships", {}))
        state.world = _deserialize_state_dict(data.get("world", {}))
        state.timeline = data.get("timeline", [])
        state.themes = _deserialize_state_dict(data.get("themes", {}))
        state.motifs = _deserialize_state_dict(data.get("motifs", {}))
        state.promises = _deserialize_state_dict(data.get("promises", {}))
        state.threats = _deserialize_state_dict(data.get("threats", {}))
        state.mysteries = _deserialize_state_dict(data.get("mysteries", {}))
        
        # Keys in JSON might be strings, cast to int for chapter summaries
        raw_summaries = data.get("chapter_summaries", {})
        state.chapter_summaries = {int(k): v for k, v in raw_summaries.items()}
        state.conflicts = _deserialize_state_dict(data.get("conflicts", {}))
        state.arcs = _deserialize_state_dict(data.get("arcs", {}))
        state.style = _deserialize_state_dict(data.get("style", {}))

        # Deserialize evidence store
        for eid, edata in data.get("evidence_store", {}).items():
            state.evidence_store[eid] = Evidence.from_dict(edata)

        return state
