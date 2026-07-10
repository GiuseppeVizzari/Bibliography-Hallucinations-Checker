"""
test_integration.py

Integration tests for the bibliography extraction pipeline.
"""
import sys
import os

# Ensure the project root is on sys.path for package imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pdf_processor import extract_bibliography
from app.checkers.extraction import extract_doi_info, heal_doi


def test_harnessing_pdf_extraction():
    """Verify P0 fix: harnessing.pdf should yield 23 references."""
    refs = extract_bibliography("PDF for test/harnessing.pdf")
    assert len(refs) == 23, f"Expected 23 references, got {len(refs)}"

    # Verify at least one reference has a DOI (P0 regression guard)
    assert any("10." in ref for ref in refs), "Expected at least one DOI in results"

    # Verify first reference content
    assert "J. Adrian" in refs[0], "First reference should be by J. Adrian"
    assert "bottlenecks" in refs[0].lower(), "First reference should mention bottlenecks"

    # Verify last reference content
    assert "A. Wang" in refs[-1], "Last reference should be by A. Wang"

    print("test_harnessing_pdf_extraction PASSED")


def test_doi_extraction():
    """P3: Validate DOI extraction with broken DOIs and edge cases."""

    # --- Test 1: Complete DOI (no break) ---
    ref = "Smith, J. (2023). Title. DOI: 10.1234/abcd.5678"
    doi, end = extract_doi_info(ref)
    assert doi == "10.1234/abcd.5678", f"Expected '10.1234/abcd.5678', got '{doi}'"
    healed, healed_end = heal_doi(doi, end, ref)
    assert healed is None, "Complete DOI should not need healing"

    # --- Test 2: Broken DOI with space after "10." ---
    ref = "Smith, J. (2023). Title. DOI: 10. 1234/abcd.5678"
    doi, end = extract_doi_info(ref)
    assert doi == "10.", f"Expected '10.', got '{doi}'"
    healed, healed_end = heal_doi(doi, end, ref)
    assert healed == "10.1234/abcd.5678", f"Expected '10.1234/abcd.5678', got '{healed}'"

    # --- Test 3: Broken DOI with newline after "10." ---
    ref = "Smith, J. (2023). Title. DOI: 10.\n1234/abcd.5678"
    doi, end = extract_doi_info(ref)
    assert doi == "10.", f"Expected '10.', got '{doi}'"
    healed, healed_end = heal_doi(doi, end, ref)
    assert healed == "10.1234/abcd.5678", f"Expected '10.1234/abcd.5678', got '{healed}'"

    # --- Test 4: DOI with hyphens ---
    ref = "Doe, J. (2022). Title. DOI: 10.1016/j.ssci.2023.106174"
    doi, end = extract_doi_info(ref)
    assert doi == "10.1016/j.ssci.2023.106174", f"Expected '10.1016/j.ssci.2023.106174', got '{doi}'"

    # --- Test 5: DOI in URL form ---
    ref = "Jones, M. (2021). Title. https://doi.org/10.1371/journal.pone.0276229"
    doi, end = extract_doi_info(ref)
    assert doi == "10.1371/journal.pone.0276229", f"Expected '10.1371/journal.pone.0276229', got '{doi}'"

    # --- Test 6: Broken DOI that cannot be healed (continuation is a stop word) ---
    ref = "Brown, T. (2020). Title. DOI: 10. is a valid point"
    doi, end = extract_doi_info(ref)
    assert doi == "10.", f"Expected '10.', got '{doi}'"
    healed, healed_end = heal_doi(doi, end, ref)
    assert healed is None, "DOI with stop-word continuation should not be healed"

    # --- Test 7: No DOI in reference ---
    ref = "Wilson, R. (2019). Title. Journal of Testing, 15(3), 45-67."
    doi, end = extract_doi_info(ref)
    assert doi is None, f"Expected None, got '{doi}'"
    assert end == 0, f"Expected end=0, got {end}"

    # --- Test 8: DOI at start of reference ---
    ref = "DOI: 10.21105/joss.02770. Smith, J. (2023). Title."
    doi, end = extract_doi_info(ref)
    assert doi == "10.21105/joss.02770", f"Expected '10.21105/joss.02770', got '{doi}'"

    # --- Test 9: DOI with semicolons and parentheses ---
    ref = "Lee, K. (2024). Title. DOI: 10.1145/3543518.3583247"
    doi, end = extract_doi_info(ref)
    assert doi == "10.1145/3543518.3583247", f"Expected '10.1145/3543518.3583247', got '{doi}'"

    print("test_doi_extraction PASSED")


if __name__ == "__main__":
    test_harnessing_pdf_extraction()
    test_doi_extraction()
