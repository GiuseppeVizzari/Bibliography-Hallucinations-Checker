"""
app/checkers/__init__.py

Public API for the checkers package.
Import check_reference from here in all callers.
"""
from .orchestrator import check_reference

__all__ = ["check_reference"]
