"""
test_normalizer.py

Tests for app/checkers/normalizer.py — normalization, similarity,
and the length-penalty for substring false positives.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.curdir))

from app.checkers.normalizer import calculate_similarity
from app.checkers.config import RELEVANCE_THRESHOLD


def test_length_penalty_for_substring():
    """When one title is a substring of another, the score should be penalized."""
    # Short title is a substring of long title
    sim = calculate_similarity("stance detection a survey", "deep learning in stance detection a survey")
    # Raw similarity would be high (substring match), but length ratio = 25/42 ≈ 0.595
    # So score should be ~0.746 * 0.595 ≈ 0.444
    assert sim < 0.5, f"Substring match should be penalized: {sim:.4f}"
    assert sim > 0.4, f"Should still have some similarity: {sim:.4f}"

    # Nearly equal lengths (within 5%) with high word overlap — no penalty
    sim2 = calculate_similarity("very long title here", "very long title there")
    assert sim2 > 0.8, f"Nearly equal-length with overlap should be high: {sim2:.4f}"


def test_false_positive_survey_titles():
    """Regression test: "Stance detection: A survey" should NOT match "Deep Learning in Stance Detection: A Survey".

    This was a real false positive where Küçük & Can (2020) "Stance detection: A survey"
    was incorrectly matched to Gera et al. (2026) "Deep Learning in Stance Detection: A Survey"
    with similarity 0.7463 (before the length penalty fix).

    After the length penalty fix:
    - Wrong paper (Gera et al.): ~0.444 (below RELEVANCE_THRESHOLD of 0.50)
    - Correct paper (Küçük & Can): 1.0 (exact match)
    """
    wrong_title = "Deep Learning in Stance Detection: A Survey"
    correct_title = "Stance detection: A survey"
    target = "Stance detection: a survey"

    # The wrong paper should score below the relevance threshold
    wrong_sim = calculate_similarity(target, wrong_title)
    assert wrong_sim < RELEVANCE_THRESHOLD, \
        f"Wrong paper should be rejected: sim={wrong_sim:.4f} >= threshold={RELEVANCE_THRESHOLD}"

    # The correct paper should score 1.0 (exact match after normalization)
    correct_sim = calculate_similarity(target, correct_title)
    assert correct_sim == 1.0, \
        f"Correct paper should be exact match: sim={correct_sim:.4f}"

    # The gap between correct and wrong should be significant
    gap = correct_sim - wrong_sim
    assert gap > 0.5, f"Gap between correct and wrong should be > 0.5: gap={gap:.4f}"


def test_length_penalty_edge_cases():
    """Edge cases for the length penalty."""
    # Identical strings — no penalty
    sim = calculate_similarity("exact match", "exact match")
    assert sim == 1.0, f"Identical strings should have similarity 1.0: {sim}"

    # Very short strings — ratio should still apply
    sim = calculate_similarity("ab", "abc")
    # length_ratio = 2/3 ≈ 0.667, raw_sim ≈ 0.667
    # score ≈ 0.667 * 0.667 ≈ 0.444
    assert sim < 0.7, f"Short substring should be penalized: {sim:.4f}"

    # Long strings with small difference — should NOT trigger penalty if ratio >= 0.95
    sim = calculate_similarity(
        "a very long title with many words",
        "a very long title with few words"
    )
    # Both ~37 chars, ratio ≈ 1.0 → no penalty
    assert sim > 0.5, f"Similar-length strings should not be penalized: {sim:.4f}"


def test_similarity_with_different_words():
    """Similarity should drop when words differ even if lengths are similar."""
    sim = calculate_similarity("machine learning survey", "natural language processing survey")
    # Same length, same suffix word, but different prefixes — moderate similarity
    assert sim < 0.6, f"Different words should reduce similarity: {sim:.4f}"
    assert sim > 0.2, f"Should still have some overlap: {sim:.4f}"


def test_similarity_with_hyphens():
    """Hyphens should be preserved in similarity comparison."""
    sim = calculate_similarity("state-of-the-art", "state-of-the-art")
    assert sim == 1.0, f"Identical hyphenated strings should match: {sim}"

    sim = calculate_similarity("state-of-the-art", "state of the art")
    # Hyphens are stripped by normalize_text, so this should be high
    assert sim > 0.8, f"Hyphenated vs spaced should be similar: {sim:.4f}"


if __name__ == "__main__":
    test_length_penalty_for_substring()
    test_false_positive_survey_titles()
    test_length_penalty_edge_cases()
    test_similarity_with_different_words()
    test_similarity_with_hyphens()
    print("All normalizer tests passed!")
