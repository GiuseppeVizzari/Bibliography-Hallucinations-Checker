"""
app/reference_checker.py  — BACKWARD COMPATIBILITY SHIM

All logic has been moved to app/checkers/. This file re-exports the public
API so that existing callers (routes.py, etc.) continue to work unchanged.

Do not add new logic here; extend the relevant module in app/checkers/ instead.
"""

# Core pipeline entry point
from app.checkers import check_reference                          # noqa: F401

# Utilities kept available for external callers
from app.checkers.extraction import (                            # noqa: F401
    extract_title_from_reference,
    extract_doi_info,
    heal_doi,
    extract_arxiv_id,
)
from app.checkers.normalizer import calculate_similarity          # noqa: F401
