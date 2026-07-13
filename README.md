# Bibliography Hallucinations Checker

A Flask web application that extracts bibliographic references from PDFs and verifies them against multiple open scholarly APIs to detect "hallucinated" (non-existent or mismatched) entries.

## Quick Start

### 1. Install the Package

Choose the installation method that suits your workflow:

#### Option A — Install from local source (recommended)

```bash
# Create virtual environment (recommended)
python -m venv .venv

# Activate the virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Install from local source
pip install .
```

This installs the `bibcheck` package and all its dependencies. The virtual environment approach is recommended because it isolates dependencies from your system Python installation and prevents conflicts with other Python projects.

#### Option B — Install via requirements.txt

```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

pip install -r requirements.txt
```

Use this approach if you want to pin exact dependency versions or manage them through the requirements file.

#### Option C — Install in development mode (editable)

```bash
python -m venv .venv
source .venv/bin/activate

# Editable install — changes to source code take effect immediately
pip install -e ".[dev]"
```

This is useful when you're actively developing the project and want to test changes without reinstalling.

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | **Yes** | Flask secret key for session cookies & CSRF protection. Generate with: `python -c "import secrets; print(secrets.token_hex(16))"` |
| `OPENALEX_EMAIL` | No | Email for OpenAlex "polite pool" access (faster responses) |
| `OPENALEX_API_KEY` | No | API key for higher OpenAlex rate limits |
| `FLASK_DEBUG` | No | Set to `1` to enable Flask debug mode (not recommended for production) |

### 3. Run the Application

```bash
python run.py
```

Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

To capture all output to a log file:

```bash
python run.py > debug.log 2>&1
```

### Production Deployment

The app includes a WSGI entry point (`wsgi.py`) for deployment with a production-grade ASGI/WSGI server such as **gunicorn**:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn (4 workers, bound to localhost)
gunicorn --workers 4 --bind 127.0.0.1:8000 wsgi:app
```

**Before deploying:**

1. Set `SECRET_KEY` to a strong, randomly generated value in your `.env` file.
2. Ensure `FLASK_DEBUG` is **not** set (or set to `0`) — debug mode must be disabled in production.
3. Place `.env` on the server with restrictive permissions (`chmod 600 .env`).
4. Put gunicorn behind a reverse proxy (nginx, Caddy) for TLS termination and static file handling.

**Docker example:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_DEBUG=0
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "wsgi:app"]
```

```bash
docker build -t bibcheck .
docker run -p 8000:8000 --env-file .env bibcheck
```

## How It Works

### Pipeline Overview

```
PDF Upload → Bibliography Detection → Reference Splitting → 
Identifier Extraction → 6-Step Verification → Similarity Scoring → Results
```

### 1. Bibliography Detection

The app parses the PDF via PyMuPDF, extracting text blocks with layout preservation. Blocks spanning more than 60% of a page's height are always kept (preventing tall content like figures or wide tables from being accidentally filtered as margins). Two-column layouts are handled by sorting blocks left-to-right, top-to-bottom. It recognises a broad set of section headers: English (`References`, `Bibliography`, `Works Cited`), Italian (`Bibliografia`, `Riferimenti`), and common typos (`Rererences`). Table-of-contents entries (containing trailing page numbers or dotted leaders) are rejected heuristically.

### 2. Appendix & Garbage Skipping

After the bibliography header, common termination keywords act as hard stop points: `Appendix`, `Annex`, `Acknowledgments`, `Biography`, `Credit Author Statement`, `Generative AI`, `Supplementary Material`, Italian equivalents (`Appendice`, `Ringraziamenti`), and others (~30 terms). Appendix table/figure captions (`Table A1`, `Fig. A2`) and pure numeric table rows (>60% numeric tokens) are filtered out to prevent false positives.

### 3. Line Number Filtering

Many PDFs include marginal or embedded line numbers (common in draft submissions and camera-ready templates). A three-layer filter removes them:

- **Layer 1 — Marginal block detection**: Narrow, purely numeric blocks positioned in the left/right margin (x < 50pt or x > page_width − 50pt) are discarded during block extraction.
- **Layer 2 — Embedded line number stripping**: Standalone 1–4 digit lines within a text block (e.g. line numbers interleaved between reference lines) are removed from the joined text before splitting.
- **Layer 3 — Per-reference cleanup**: Each extracted reference is individually scrubbed of trailing standalone numbers.

### 4. Reference Splitting

The app auto-detects the citation style:

- **Bracketed numbers** – `[1]`, `[2]`, ... (IEEE / Vancouver)
- **Plain numbers** – `1.`, `2.`, ... (numbered lists)
- **Author-year** – `[Author, Year]`, `[Author et al., Year]` (APA, some LaTeX templates)
- **Block-based** – one block per reference, used by Chicago and similar author–date styles

Hyphenated words broken across PDF lines (e.g. `be-\nhaviors`) are automatically rejoined.

### 5. Identifier Extraction

DOIs, arXiv IDs, and bare URLs are extracted from each reference. A multi-strategy **title extraction** cascade (8 strategies) handles quoted titles, author-year punctuation (APA/Chicago), comma-delimited styles, content-based heuristics, and colon-separated LNCS/Springer formats, while rejecting false positives such as author lists, page-number ranges, and venue abbreviations (e.g. "Proceedings of the 2024 ACM Conference" is not returned as a title).

### 6. Six-Step Verification Pipeline

Each reference is checked in priority order:

| Step | Method | Source | Notes |
|------|--------|--------|-------|
| 1 | DOI lookup | OpenAlex → Crossref / DataCite | Zenodo DOIs (10.5281) route to DataCite first |
| 2 | DOI healing | (retry cycle) | Reconstructs DOIs broken by PDF line-wrapping, including `10.` prefix splits |
| 3 | arXiv ID | arXiv API | Direct Atom feed lookup |
| 4 | URL resource | Direct fetch | Downloads HTML/PDF from a bare URL in the reference, follows meta-refresh redirects, extracts `<title>`, compares against reference; tries all non-DOI/non-arXiv URLs |
| 5 | Title search | OpenAlex → DBLP | OpenAlex title search; falls back to DBLP for CS conference/journal proceedings |
| 5b | Title search fallback | DBLP | CS conference/journal proceedings fallback when OpenAlex returns a weak match |
| 6 | Web fallback | DuckDuckGo + scraping | Web search with page-title verification for non-academic references (last resort) |

### 7. Similarity Scoring

Every successfully matched result is compared against the extracted reference title using `difflib.SequenceMatcher`. The score determines the visual badge in the UI.

## Project Structure

```
app/
├── __init__.py                   # Flask app factory (CSRF protection, SECRET_KEY from env)
├── routes.py                     # Upload route + parallel processing (ThreadPoolExecutor)
├── pdf_processor.py              # PDF parsing, bibliography detection, reference splitting
│
├── templates/
│   ├── base.html                 # Base template
│   ├── index.html                # Upload page (with CSRF token)
│   ├── processing.html           # Progress indicator during verification
│   └── results.html              # Results table
│
└── checkers/
    ├── __init__.py               # Exports check_reference
    ├── config.py                 # Centralized thresholds, retry logic, rate limits
    ├── orchestrator.py           # 6-step verification pipeline + cached backend singletons
    ├── extraction.py             # DOI/arXiv ID/title extraction heuristics
    ├── normalizer.py             # Unicode ligature decomposition, quote normalization, similarity
    │
    └── backends/
        ├── __init__.py           # Exports all backend classes
        ├── base.py               # BackendService base class (DOI, title, URL, identifier lookups)
        ├── openalex.py           # OpenAlex API (DOI lookup + title search)
        ├── crossref.py           # Crossref API via habanero
        ├── datacite.py           # DataCite REST API
        ├── arxiv.py              # arXiv Atom feed API (HTTPS, rate-limited)
        ├── url_checker.py        # Direct URL fetcher (HTML/PDF)
        └── web_fallback.py       # General web search and scraping fallback
```

## Features

- ✅ **Hallucination Detection**: Visual cues (badges and row highlighting) flag found references that differ significantly from the PDF text.
- ✅ **Parallel Processing**: References are verified concurrently (4 workers) for significantly faster processing.
- ✅ **Progress Indicator**: Real-time progress bar shows verification status during processing, powered by AJAX polling for smooth, up-to-the-second updates.
- ✅ **AJAX Polling**: Background processing with automatic progress polling — the page updates in real-time without a full reload.
- ✅ **Multi-language Bibliography Headers**: Supports English and Italian section titles, plus common OCR/typo variants.
- ✅ **Appendix Termination**: Automatically stops collecting references at ~30 termination keywords, including lettered appendix tables and numeric table rows.
- ✅ **Two-Column Layout Support**: Left-to-right, top-to-bottom block sorting handles common PDF layouts.
- ✅ **Line Number Filtering**: Three-layer filter removes marginal and embedded line numbers that would otherwise corrupt reference text.
- ✅ **Hyphenated Word Rejoining**: Words broken across PDF lines with hyphens are rejoined, including uppercase continuations (e.g. `Multi-\nTarget` → `MultiTarget`) for title-case words common in reference titles.
- ✅ **DOI Healing**: Automatically fixes broken DOIs caused by PDF line-wrapping or spaces. Trailing punctuation (`.`, `,`, `;`, `)`, `]`) is stripped from extracted DOIs to prevent false mismatches.
- ✅ **Multi-Page Reference Merging**: References that span page boundaries are automatically detected and merged by comparing consecutive block page indices.
- ✅ **Seven-Engine Search**: OpenAlex, Crossref, DataCite, arXiv, DBLP (CS conference/journal proceedings), web search fallback, and direct URL resource fetching.
- ✅ **Partial arXiv Identifiers**: Enhanced support for extracting arXiv IDs from partial identifiers in reference text (e.g., "arXiv:2403.02221" or "CoRR, abs/1810.04805").
- ✅ **Rate Limiting & Retry**: Automatic exponential backoff for rate-limited APIs (arXiv, DataCite, OpenAlex).
- ✅ **Relevance Gate**: Title search results with similarity < 0.35 are automatically discarded to avoid false matches.
- ✅ **Clickable Links in Results**: Both the original reference column (DOI / arXiv / URL) and the found paper column (title link + source link) provide direct hyperlinks.
- ✅ **Back-to-Top Button**: A floating button appears while scrolling the results page for quick navigation.
- ✅ **Improved Visibility**: Updated UI colors (orange vs white) for better legibility of similarity scores and status badges.
- ✅ **CSRF Protection**: Form submissions are protected against cross-site request forgery attacks.
- ✅ **Secure by Default**: SECRET_KEY sourced from environment variables, debug mode disabled by default.
- ✅ **No Scholarly API Keys Required**: OpenAlex, Crossref, DataCite, and arXiv are free and open. Optional API keys improve rate limits.
- ✅ **Web Search Fallback**: For references not found in academic APIs, the app performs a targeted web search and similarity analysis on page titles.
- ✅ **Intelligent Fallback**: Automatically triggers web search if academic results are found but have low similarity (< 60%), preventing false positives from blocking discovery.

## Understanding Results

| Similarity | Meaning |
|---|---|
| **≥ 80%** 🟢 | Strong match — very likely the correct paper. |
| **60–80%** 🟡 | Moderate match — probably correct, but worth a manual check. |
| **< 60%** 🔴 | Low match — potential hallucination or wrong paper returned. Row is highlighted and shows a **"Check Match"** badge. |

### Result Table Columns

- **Extracted Reference** — raw text pulled from the PDF. A 🔗 **Source** badge appears below when a DOI, arXiv ID, or URL was found in the original text.
- **Status** — `Found`, `Check Match`, `Not Found`, `Skipped`, or `Error`.
- **Source** — which API resolved the reference (OpenAlex, Crossref, DataCite, arXiv, DBLP, or URL Resource).
- **Online Data** — the title (clickable link to the paper), authors, venue, year, and similarity score.

## Troubleshooting

### "No references found"

- The app looks for `References`, `Bibliography`, `Works Cited`, `Bibliografia`, and `Riferimenti`. If the PDF uses a different heading, the section will not be detected.
- Try checking the PDF manually and confirming the section header text.

### Too many false-positive references (appendix content included)

- Run with debug logging (`python run.py > debug.log 2>&1`) and inspect lines marked `[DEBUG] INCLUDE block` after the bibliography header. These show exactly what text the parser is collecting. If appendix blocks appear, their heading text can be added to the termination keyword list in `app/pdf_processor.py`.

### Port 5000 in Use (macOS)

- If you see "Address already in use", disable **AirPlay Receiver** in System Settings → General → AirDrop & Handoff, as it often occupies port 5000.

### Import Errors with `ddgs`

If you encounter errors like `ModuleNotFoundError: No module named 'ddgs'`, make sure you're using the virtual environment and have installed all dependencies:

```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install .
```

## Acknowledgments

This project is built using several powerful open-source libraries and APIs:

- **[PyMuPDF (fitz)](https://github.com/pymupdf/PyMuPDF)**: For extracting text and metadata from PDF documents.
- **[Flask](https://flask.palletsprojects.com/)**: To provide the web-based user interface and application routing.
- **[pyalex](https://github.com/jperkel/pyalex)**: Python client for the **[OpenAlex API](https://openalex.org/)**, used for high-speed scholarly work verification.
- **[habanero](https://github.com/sckott/habanero)**: A low-level client for the **[Crossref API](https://www.crossref.org/)**, providing reliable fallback for DOI lookups.
- **[DataCite API](https://support.datacite.org/docs/api)**: Used for verifying Zenodo and other repository-hosted DOIs.
- **[arXiv API](https://arxiv.org/help/api)**: Used for direct verification of pre-print identifiers.
- **[DBLP API](https://dblp.org/)**: Used for verifying computer science conference and journal proceedings not well covered by OpenAlex.
- **[python-dotenv](https://github.com/theskumar/python-dotenv)**: For managing environment variables securely.
- **[Requests](https://requests.readthedocs.io/)**: To handle all API communications.
- **[beautifulsoup4](https://www.beautifulsoup.com/)**: For parsing HTML content during web fallback.
- **[duckduckgo-search (ddgs)](https://pypi.org/project/duckduckgo-search/)**: For performing privacy-respecting web searches without an API key.
