"""
NLP Processor — spaCy pipeline wrapper.

Wraps spaCy model loading and text processing. Provides POS tagging,
dependency parsing, and lemmatization as evidence for downstream
narrative state interpretation.

This is a thin wrapper — it produces linguistic annotations,
not narrative understanding.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("NarrativeEngine.Pipeline.NLP")


class NLPProcessor:
    """
    Wraps spaCy for core NLP tasks (tokenization, POS, dependencies).

    Usage:
        nlp = NLPProcessor()
        doc = nlp.process("Alice walked to the Silver Gate.")
        for token in doc:
            print(token.text, token.pos_, token.dep_)
    """

    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Args:
            model_name: spaCy model to load. Defaults to en_core_web_sm.
        """
        self._model_name = model_name
        self._nlp = None

    def _ensure_loaded(self):
        """Lazy-load the spaCy model on first use."""
        if self._nlp is None:
            try:
                import spacy
                logger.info(f"Loading spaCy model: {self._model_name}")
                self._nlp = spacy.load(self._model_name)
                logger.info(f"spaCy model loaded successfully")
            except ImportError:
                raise ImportError(
                    "spaCy is required. Install with: pip install spacy && "
                    "python -m spacy download en_core_web_sm"
                )
            except OSError:
                raise OSError(
                    f"spaCy model '{self._model_name}' not found. "
                    f"Download it with: python -m spacy download {self._model_name}"
                )

    @property
    def nlp(self):
        """Access the underlying spaCy Language object."""
        self._ensure_loaded()
        return self._nlp

    def process(self, text: str):
        """
        Process text through the spaCy pipeline.

        Args:
            text: Input text to process.

        Returns:
            spaCy Doc object with linguistic annotations.
        """
        self._ensure_loaded()
        logger.debug(f"Processing text ({len(text)} chars) through spaCy")
        doc = self._nlp(text)
        logger.debug(f"Produced {len(doc)} tokens, {len(list(doc.sents))} sentences")
        return doc

    def extract_noun_chunks(self, doc) -> list:
        """Extract noun chunks from a spaCy Doc."""
        return [
            {
                "text": chunk.text,
                "root": chunk.root.text,
                "root_pos": chunk.root.pos_,
                "start": chunk.start_char,
                "end": chunk.end_char,
            }
            for chunk in doc.noun_chunks
        ]

    def extract_subject_verb_object(self, doc) -> list:
        """
        Extract basic (subject, verb, object) triples from dependency parse.

        This produces evidence — not final relationship state.
        """
        triples = []
        for token in doc:
            if token.dep_ in ("nsubj", "nsubjpass"):
                subject = token.text
                verb = token.head.text
                
                # Find direct objects and prepositional objects/dative targets
                objects = []
                for child in token.head.children:
                    if child.dep_ in ("dobj", "attr", "pobj"):
                        objects.append(child.text)
                    elif child.dep_ in ("prep", "dative"):
                        for grandchild in child.children:
                            if grandchild.dep_ in ("pobj", "dobj"):
                                objects.append(grandchild.text)
                                
                for obj in objects:
                    triples.append({
                        "subject": subject,
                        "verb": verb,
                        "object": obj,
                        "sentence": token.sent.text,
                    })
        return triples
