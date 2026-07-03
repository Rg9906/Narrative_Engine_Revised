"""
Narrative Graph — NetworkX-based knowledge graph.

Connects characters, events, locations, themes, promises into an
interconnected web of narrative understanding.

Implementation: Phase 9
"""

from __future__ import annotations

import logging

logger = logging.getLogger("NarrativeEngine.Engines.Graph")


class NarrativeGraph:
    """Maintains a knowledge graph of all narrative elements."""

    def __init__(self):
        try:
            import networkx as nx
            self._graph = nx.DiGraph()
        except ImportError:
            raise ImportError("NetworkX is required. Install with: pip install networkx")

    def add_node(self, node_id: str, node_type: str, **attributes):
        """Add a narrative element to the graph."""
        self._graph.add_node(node_id, type=node_type, **attributes)

    def add_edge(self, source: str, target: str, relationship: str, **attributes):
        """Add a relationship between narrative elements."""
        self._graph.add_edge(source, target, relationship=relationship, **attributes)

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()
