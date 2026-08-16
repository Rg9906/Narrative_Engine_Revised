"""Unit tests for the api/ FastAPI layer.

Kept deliberately narrow: this project's API layer is a thin read/ingest
wrapper over data/*.json (see api/main.py's own module docstring), so these
tests target specific, security- or correctness-relevant logic rather than
standing up a full endpoint-by-endpoint TestClient suite.
"""

from api.main import _safe_upload_filename


class TestSafeUploadFilename:
    """Regression coverage for a path-traversal / arbitrary-write bug found by
    a self-review pass: the chapter ingestion endpoint used to join the
    fully attacker-controlled upload filename straight into a filesystem
    path with no sanitization -- both "../../evil.txt" (traversal) and an
    absolute path as the filename (which pathlib's `/` operator resolves by
    silently discarding the base directory entirely) resulted in writing
    outside the intended data/chapters directory."""

    def test_plain_filename_passes_through(self):
        assert _safe_upload_filename("chapter_05.txt") == "chapter_05.txt"

    def test_relative_traversal_is_stripped_to_basename(self):
        assert _safe_upload_filename("../../../../evil.txt") == "evil.txt"
        assert _safe_upload_filename("..\\..\\evil.txt") == "evil.txt"

    def test_absolute_windows_path_is_stripped_to_basename(self):
        assert _safe_upload_filename("C:\\Windows\\System32\\evil.txt") == "evil.txt"

    def test_absolute_posix_path_is_stripped_to_basename(self):
        assert _safe_upload_filename("/etc/passwd.txt") == "passwd.txt"

    def test_none_or_empty_filename_gets_a_default(self):
        assert _safe_upload_filename(None) == "chapter.txt"
        assert _safe_upload_filename("") == "chapter.txt"
