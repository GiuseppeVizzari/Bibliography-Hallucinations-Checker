"""
app/checkers/backends/datacite.py

DataCite API backend — DOI lookup via REST API.
"""

import logging
import requests
from ..normalizer import strip_doi_punctuation
from .base import BackendService

logger = logging.getLogger(__name__)

_API_BASE = "https://api.datacite.org/dois"


class DataCiteBackend(BackendService):
    """DataCite API backend implementation."""

    def lookup_by_doi(self, doi: str) -> dict:
        """Fetch a work from DataCite by its DOI."""
        try:
            doi_query = strip_doi_punctuation(doi)
            logger.debug(f"  DataCite DOI lookup: {doi_query}...")
            response = requests.get(f"{_API_BASE}/{doi_query}", timeout=10)

            if response.status_code != 200:
                return {"status": "not_found"}

            data = response.json().get('data', {})
            attributes = data.get('attributes', {})

            # Title
            titles = attributes.get('titles', [])
            work_title = titles[0].get('title', 'N/A') if titles else 'N/A'
            logger.debug(f"  ✓ Found in DataCite: {work_title[:60]}...")

            # Authors (up to 3 + "et al.")
            creators = attributes.get('creators', [])
            authors = 'N/A'
            if creators:
                names = [c.get('name', '') for c in creators[:3] if c.get('name')]
                if names:
                    authors = ', '.join(names)
                    if len(creators) > 3:
                        authors += ', et al.'

            return {
                "status": "found",
                "source": "DataCite",
                "title": work_title,
                "author": authors,
                "pub_year": str(attributes.get('publicationYear', 'N/A')),
                "venue": attributes.get('publisher', 'N/A'),
                "url": f"https://doi.org/{doi_query}",
            }

        except Exception as e:
            err = str(e)
            logger.debug(f"  - DataCite error: {err[:50]}...")
            return {"status": "error", "message": err}

    def lookup_by_id(self, identifier: str) -> dict:
        """Lookup by identifier (not used for DataCite)."""
        # For DataCite, DOI lookups are preferred
        return self.lookup_by_doi(identifier)

    def lookup_by_title(self, title: str) -> dict:
        """Title search not implemented for DataCite."""
        return {"status": "not_found"}