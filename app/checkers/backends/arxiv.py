"""
app/checkers/backends/arxiv.py

arXiv API backend — lookup by arXiv ID via the official Atom feed API.
"""
import requests
import xml.etree.ElementTree as ET

_API_URL = "http://export.arxiv.org/api/query"
_NS = {'atom': 'http://www.w3.org/2005/Atom'}


def lookup_by_id(arxiv_id: str) -> dict:
    """Fetch a paper from the arXiv API by its ID (e.g. '2412.11814')."""
    try:
        print(f"  arXiv API lookup: {arxiv_id}...")
        response = requests.get(_API_URL, params={"id_list": arxiv_id}, timeout=10)

        if response.status_code != 200:
            return {"status": "not_found"}

        root = ET.fromstring(response.content)
        entry = root.find('atom:entry', _NS)

        if entry is None:
            return {"status": "not_found"}

        title_elem = entry.find('atom:title', _NS)
        if title_elem is None or not title_elem.text:
            return {"status": "not_found"}

        work_title = title_elem.text.strip().replace('\n', ' ')

        # Authors (up to 3 + "et al.")
        author_elems = entry.findall('atom:author', _NS)
        names = []
        for auth in author_elems[:3]:
            name_elem = auth.find('atom:name', _NS)
            if name_elem is not None:
                names.append(name_elem.text)
        authors = ', '.join(names) if names else 'N/A'
        if len(author_elems) > 3:
            authors += ', et al.'

        # Publication year
        published = entry.find('atom:published', _NS)
        pub_year = published.text[:4] if published is not None else 'N/A'

        print(f"  ✓ Found in arXiv: {work_title[:60]}...")

        return {
            "status": "found",
            "source": "arXiv",
            "title": work_title,
            "author": authors,
            "pub_year": pub_year,
            "venue": "arXiv",
            "url": f"https://arxiv.org/abs/{arxiv_id}",
        }

    except Exception as e:
        print(f"  - arXiv API error: {str(e)[:50]}...")
        return {"status": "error", "message": str(e)}
