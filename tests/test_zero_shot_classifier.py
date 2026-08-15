"""Unit tests for the optional zero-shot classifier wrapper and its use in
ThemeMemory/MysteryMemory. These tests never download the real model —
they force the unavailable path or mock `classify_batch` with canned scores,
so they run identically with or without `transformers` installed."""

import pytest

from src.utils.zero_shot_classifier import ZeroShotClassifier, get_classifier, reset_classifier
from src.memory.theme_memory import ThemeMemory
from src.memory.mystery_memory import MysteryMemory
from src.models.state import ChapterData


@pytest.fixture(autouse=True)
def _reset_classifier_singleton():
    reset_classifier()
    yield
    reset_classifier()


def _chapter(text: str, sentences=None) -> ChapterData:
    return ChapterData(
        chapter_number=1,
        source_name="test.txt",
        raw_text=text,
        sentences=sentences if sentences is not None else [text],
    )


class TestZeroShotClassifierFallback:
    def test_unavailable_when_transformers_missing_or_load_fails(self, monkeypatch):
        """If the underlying `transformers.pipeline` call raises for any reason,
        `available` becomes False exactly once and stays False — no exception
        propagates."""
        classifier = ZeroShotClassifier()

        def _boom(*args, **kwargs):
            raise RuntimeError("no internet")

        # Patch the transformers import site itself so we don't need the real
        # package installed to exercise this path.
        import sys
        import types

        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = _boom
        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        assert classifier.available is False
        # Second access must not re-attempt loading (no repeated exception risk).
        assert classifier.available is False
        assert classifier.classify_batch(["hello"], ["a", "b"]) is None

    def test_classify_batch_returns_none_when_unavailable(self):
        classifier = ZeroShotClassifier()
        classifier._load_attempted = True
        classifier._available = False
        assert classifier.classify_batch(["hello"], ["a", "b"]) is None

    def test_get_classifier_is_a_singleton(self):
        a = get_classifier()
        b = get_classifier()
        assert a is b


class TestThemeMemoryClassifierFallback:
    def test_theme_detection_matches_keyword_baseline_when_classifier_unavailable(self, monkeypatch):
        """With the classifier forced unavailable, ThemeMemory must behave
        exactly as the pre-upgrade keyword-only implementation did."""
        monkeypatch.setattr(
            "src.memory.theme_memory.get_classifier",
            lambda: types_stub_unavailable(),
        )
        memory = ThemeMemory()
        chapter = _chapter(
            "Love and devotion filled her heart. Passion consumed him entirely.",
            sentences=["Love and devotion filled her heart.", "Passion consumed him entirely."],
        )
        changes = memory.update_from_chapter(chapter, chapter_num=1)
        assert any(c.target_id == "theme_love" for c in changes)

    def test_theme_detection_uses_classifier_scores_when_available(self, monkeypatch):
        """With a mocked classifier reporting a high 'love' score, a theme
        should be introduced even without exact keyword matches."""
        fake = _FakeClassifier(
            available=True,
            batch_result=[
                {"love": 0.95, "death": 0.05},
                {"love": 0.90, "death": 0.02},
            ],
        )
        monkeypatch.setattr("src.memory.theme_memory.get_classifier", lambda: fake)

        memory = ThemeMemory()
        # Deliberately no theme keywords in the raw text — only the mocked
        # classifier scores should drive detection.
        chapter = _chapter(
            "Two sentences with no literal theme keywords whatsoever here.",
            sentences=["Sentence one here now.", "Sentence two here now."],
        )
        changes = memory.update_from_chapter(chapter, chapter_num=1)
        assert any(c.target_id == "theme_love" for c in changes)
        assert not any(c.target_id == "theme_death" for c in changes)


class TestMysteryMemoryClassifierFallback:
    def test_mystery_detection_matches_keyword_baseline_when_classifier_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "src.memory.mystery_memory.get_classifier",
            lambda: types_stub_unavailable(),
        )
        memory = MysteryMemory()
        chapter = _chapter(
            "Who killed him?",
            sentences=["Who killed him?"],
        )
        changes = memory.update_from_chapter(chapter, chapter_num=1)
        assert any(c.field_key == "mystery_text" for c in changes)

    def test_mystery_detection_uses_classifier_scores_when_available(self, monkeypatch):
        """A sentence with no keyword/question-mark trigger should still be
        flagged as a mystery when the mocked classifier scores it highly."""
        fake = _FakeClassifier(
            available=True,
            batch_result=[{
                "poses an unresolved mystery or question": 0.9,
                "reveals a clue or piece of evidence": 0.1,
                "resolves or reveals a secret": 0.05,
            }],
        )
        monkeypatch.setattr("src.memory.mystery_memory.get_classifier", lambda: fake)

        memory = MysteryMemory()
        sentence = "There was something unsettling about the locked room nobody could explain."
        chapter = _chapter(sentence, sentences=[sentence])
        changes = memory.update_from_chapter(chapter, chapter_num=1)
        assert any(c.field_key == "mystery_text" and c.new_value == sentence for c in changes)


def types_stub_unavailable():
    return _FakeClassifier(available=False, batch_result=None)


class _FakeClassifier:
    def __init__(self, available: bool, batch_result):
        self._available = available
        self._batch_result = batch_result

    @property
    def available(self) -> bool:
        return self._available

    def classify_batch(self, texts, labels, multi_label=True):
        if not self._available:
            return None
        return self._batch_result
