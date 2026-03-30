"""
app/checkers/backends/datacite.py

DataCite API backend — DOI lookup via REST API.
"""
import requests


_API_BASE = "https://api.datacite.org/dois"


def lookup_by_doi(doi: str) -> dict:
    """Fetch a work from DataCite by its DOI."""
    try:
        doi_query = doi.rstrip('.,;)]')
        print(f"  DataCite DOI lookup: {doi_query}...")
        response = requests.get(f"{_API_BASE}/{doi_query}", timeout=10)

        if response.status_code != 200:
            return {"status": "not_found"}

        data = response.json().get('data', {})
        attributes = data.get('attributes', {})

        # Title
        titles = attributes.get('titles', [])
        work_title = titles[0].get('title', 'N/A') if titles else 'N/A'
        print(f"  ✓ Found in DataCite: {work_title[:60]}...")

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
        print(f"  - DataCite error: {err[:50]}...")
        return {"status": "error", "message": err}
