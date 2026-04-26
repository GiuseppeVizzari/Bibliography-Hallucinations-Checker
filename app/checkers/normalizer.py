"""
app/checkers/normalizer.py

Text normalization utilities shared across the checker pipeline.
"""
import re
import unicodedata
from difflib import SequenceMatcher


def normalize_ligatures(text: str) -> str:
    """Decomposes Unicode ligatures like 'ﬁ' into 'fi', 'ﬂ' into 'fl', etc."""
    if not text:
        return ""
    return unicodedata.normalize('NFKD', text)


def normalize_quotes(text: str) -> str:
    """
    Replaces typographic/curly quotes and apostrophes with their plain
    ASCII equivalents so API queries are not broken by fancy Unicode.
    """
    return (
        text
        .replace('\u2019', "'")   # right single quotation mark → '
        .replace('\u2018', "'")   # left single quotation mark  → '
        .replace('\u201c', '"')   # left double quotation mark  → "
        .replace('\u201d', '"')   # right double quotation mark → "
    )


def normalize_text(text: str) -> str:
    """
    Strips punctuation and converts to lowercase for fuzzy comparison.
    """
    clean = re.sub(r'[^\w\s]', '', text)
    return clean.lower().strip()


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Computes a [0, 1] similarity score between two strings using
    SequenceMatcher on normalized versions of the inputs.
    """
    if not text1 or not text2:
        return 0.0

    s1 = normalize_text(text1)
    s2 = normalize_text(text2)

    # Fall back to raw lowercase if normalization empties a string
    if not s1 or not s2:
        s1 = text1.lower().strip()
        s2 = text2.lower().strip()

    return SequenceMatcher(None, s1, s2).ratio()
