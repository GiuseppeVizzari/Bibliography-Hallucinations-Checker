"""
app/checkers/backends/crossref.py

Crossref API backend — DOI lookup via habanero.
"""
from habanero import Crossref

_cr = Crossref()


def lookup_by_doi(doi: str) -> dict:
    """Fetch a work from Crossref by its DOI."""
    try:
        doi_query = doi.rstrip('.,;)]')
        print(f"  Crossref DOI lookup: {doi_query}...")
        res = _cr.works(ids=doi_query)

        if not (res and 'message' in res):
            return {"status": "not_found"}

        work = res['message']

        # Title
        title_list = work.get('title', ['N/A'])
        work_title = title_list[0] if title_list else 'N/A'
        print(f"  ✓ Found in Crossref: {work_title[:60]}...")

        # Authors (up to 3 + "et al.")
        author_list = work.get('author', [])
        authors = 'N/A'
        if author_list:
            names = []
            for auth in author_list[:3]:
                given = auth.get('given', '')
                family = auth.get('family', '')
                if given and family:
                    names.append(f"{given} {family}")
                elif family:
                    names.append(family)
            if names:
                authors = ', '.join(names)
                if len(author_list) > 3:
                    authors += ', et al.'

        # Publication year
        published = (
            work.get('published-print')
            or work.get('published-online')
            or work.get('issued')
        )
        pub_year = 'N/A'
        if published and 'date-parts' in published:
            try:
                pub_year = str(published['date-parts'][0][0])
            except (IndexError, TypeError):
                pass

        # Venue
        container_titles = work.get('container-title', [])
        venue = container_titles[0] if container_titles else 'N/A'

        return {
            "status": "found",
            "source": "Crossref",
            "title": work_title,
            "author": authors,
            "pub_year": pub_year,
            "venue": venue,
            "url": work.get('URL', f"https://doi.org/{doi_query}"),
        }

    except Exception as e:
        err = str(e)
        if "404" in err:
            return {"status": "not_found"}
        print(f"  - Crossref error: {err[:50]}...")
        return {"status": "error", "message": err}
