"""
app/checkers/backends/base.py

Base interface for all backend services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BackendService(ABC):
    """Base interface for all backend services."""

    @abstractmethod
    def lookup_by_doi(self, doi: str) -> Dict[str, Any]:
        """Lookup a work by DOI."""
        pass

    @abstractmethod
    def lookup_by_id(self, identifier: str) -> Dict[str, Any]:
        """Lookup a work by identifier."""
        pass

    @abstractmethod
    def lookup_by_title(self, title: str, full_ref: str = "") -> Dict[str, Any]:
        """Lookup a work by title. ``full_ref`` may be passed for richer context."""
        pass

    def lookup_by_url(self, url: str, reference_title: str) -> Dict[str, Any]:
        """Verify a URL resource against a reference title (optional capability)."""
        return {"status": "not_found"}

    def extract_urls(self, ref_text: str) -> List[str]:
        """Extract non-DOI/non-arXiv URLs from reference text (optional capability)."""
        return []
