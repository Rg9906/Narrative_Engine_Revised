"""Utility helper functions for the Narrative Intelligence Engine."""

import hashlib

def stable_hash(text: str) -> str:
    """
    Generate a stable, deterministic 16-character hexadecimal hash for a string.
    
    This is used to create persistent IDs that remain constant across different
    runs of the Python interpreter, unlike Python's built-in hash() which is
    randomized by default.
    """
    if not text:
        return ""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:16]
