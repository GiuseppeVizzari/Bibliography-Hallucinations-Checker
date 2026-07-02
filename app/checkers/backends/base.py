"""
app/checkers/backends/base.py

Base interface for all backend services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

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
    def lookup_by_title(self, title: str) -> Dict[str, Any]:
        """Lookup a work by title."""
        pass