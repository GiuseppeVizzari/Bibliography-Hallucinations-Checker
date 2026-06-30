# Bibliography Hallucinations Checker

A Flask web application that extracts bibliographic references from PDFs and verifies them against multiple open scholarly APIs to detect "hallucinated" (non-existent or mismatched) entries.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure OpenAlex (Optional)
The application uses **OpenAlex** for high-speed reference verification. To get even faster responses (access to the "polito pool"), add your email and API key to the `.env` file:

```env
OPENALEX_EMAIL=your-email@example.com
OPENALEX_API_KEY=your-api-key
```

### 3. Run the Application

```bash
python run.py
```

Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

To capture all output to a log file:

```bash
python run.py > debug.log 2>&1
```

## How It Works

### Pipeline Overview

```
PDF Upload → Bibliography Detection → Reference Splitting → 
Identifier Extraction → 5-Step Verification → Similarity Scoring → Results
```

### 1. Bibliography Detection

The app parses the PDF via PyMuPDF, extracting text blocks with layout preservation. Two-column layouts are handled by sorting blocks left-to-right, top-to-bottom. It recognises a broad set of section headers: English (`References`, `Bibliography`, `Works Cited`), Italian (`Bibliografia`, `Riferimenti`), and common typos (`Rererences`). Table-of-contents entries (containing trailing page numbers or dotted leaders) are rejected heuristically.

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

DOIs, arXiv IDs, and bare URLs are extracted from each reference. A multi-strategy **title extraction** cascade (8 strategies) handles quoted titles, author-year punctuation (APA/Chicago), comma-delimited styles, content-based heuristics, and colon-separated LNCS/Springer formats, while rejecting false positives such as author lists, page-number ranges, and venue abbreviations.

### 6. Five-Step Verification Pipeline

Each reference is checked in priority order:

| Step | Method | Source | Notes |
|------|--------|--------|-------|
| 1 | DOI lookup | OpenAlex → Crossref / DataCite | Zenodo DOIs (10.5281) route to DataCite first |
| 2 | DOI healing | (retry cycle) | Reconstructs DOIs broken by PDF line-wrapping/spaces |
| 3 | arXiv ID | arXiv API | Direct Atom feed lookup |
| 4 | Title search | OpenAlex → Web Search | OpenAlex title search; falls back to DuckDuckGo web search if no match or similarity < 0.6 |
| 5 | URL resource | Direct fetch | Downloads HTML/PDF from a bare URL, extracts `<title>`, compares against reference |

### 7. Similarity Scoring

Every successfully matched result is compared against the extracted reference title using `difflib.SequenceMatcher`. The score determines the visual badge in the UI.

## Project Structure

```
app/
├── __init__.py                   # Flask app factory (16 MB upload limit, 413 error handler)
├── routes.py                     # Upload route + processing loop
├── pdf_processor.py              # PDF parsing, bibliography detection, reference splitting
│
└── checkers/
    ├── __init__.py               # Exports check_reference
    ├── orchestrator.py           # 5-step verification pipeline
    ├── extraction.py             # DOI/arXiv ID/title extraction heuristics
    ├── normalizer.py             # Unicode ligature decomposition, quote normalization, similarity
    │
    └── backends/
        ├── openalex.py           # OpenAlex API (DOI lookup + title search)
        ├── crossref.py           # Crossref API via habanero
        ├── datacite.py           # DataCite REST API
        ├── arxiv.py              # arXiv Atom feed API
        ├── arxiv.py              # arXiv Atom feed API
        └── url_checker.py        # Direct URL fetcher (HTML/PDF)
        └── web_fallback.py           # General web search and scraping fallback
```

## Features

- ✅ **Hallucination Detection**: Visual cues (badges and row highlighting) flag found references that differ significantly from the PDF text.
- ✅ **Multi-language Bibliography Headers**: Supports English and Italian section titles, plus common OCR/typo variants.
- ✅ **Appendix Termination**: Automatically stops collecting references at ~30 termination keywords, including lettered appendix tables and numeric table rows.
- ✅ **Two-Column Layout Support**: Left-to-right, top-to-bottom block sorting handles common PDF layouts.
- ✅ **Line Number Filtering**: Three-layer filter removes marginal and embedded line numbers that would otherwise corrupt reference text.
- ✅ **DOI Healing**: Automatically fixes broken DOIs caused by PDF line-wrapping or spaces.
- ✅ **Five-Engine Search**: OpenAlex, Crossref, DataCite, arXiv, and direct URL resource fetching.
- ✅ **Partial ARXIV Identifiers**: Enhanced support for extracting arXiv IDs from partial identifiers in reference text (e.g., "arXiv:2403.02221" or "CoRR, abs/1810.04805").
- ✅ **Relevance Gate**: Title search results with similarity < 0.35 are automatically discarded to avoid false matches.
- ✅ **Clickable Links in Results**: Both the original reference column (DOI / arXiv / URL) and the found paper column (title link + source link) provide direct hyperlinks.
- ✅ **Back-to-Top Button**: A floating button appears while scrolling the results page for quick navigation.
- ✅ **Improved Visibility**: Updated UI colors (orange vs white) for better legibility of similarity scores and status badges.
- ✅ **No API Keys Required**: Uses open scholarly APIs.
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
- **Source** — which API resolved the reference (OpenAlex, Crossref, DataCite, arXiv, or URL Resource).
- **Online Data** — the title (clickable link to the paper), authors, venue, year, and similarity score.

## Troubleshooting

### "No references found"

- The app looks for `References`, `Bibliography`, `Works Cited`, `Bibliografia`, and `Riferimenti`. If the PDF uses a different heading, the section will not be detected.
- Try checking the PDF manually and confirming the section header text.

### Too many false-positive references (appendix content included)

- Run with debug logging (`python run.py > debug.log 2>&1`) and inspect lines marked `[DEBUG] INCLUDE block` after the bibliography header. These show exactly what text the parser is collecting. If appendix blocks appear, their heading text can be added to the termination keyword list in `app/pdf_processor.py`.

### Port 5000 in Use (macOS)

- If you see "Address already in use", disable **AirPlay Receiver** in System Settings → General → AirDrop & Handoff, as it often occupies port 5000.

## Acknowledgments

This project is built using several powerful open-source libraries and APIs:

- **[PyMuPDF (fitz)](https://github.com/pymupdf/PyMuPDF)**: For extracting text and metadata from PDF documents.
- **[Flask](https://flask.palletsprojects.com/)**: To provide the web-based user interface and application routing.
- **[pyalex](https://github.com/jperkel/pyalex)**: Python client for the **[OpenAlex API](https://openalex.org/)**, used for high-speed scholarly work verification.
- **[habanero](https://github.com/sckott/habanero)**: A low-level client for the **[Crossref API](https://www.crossref.org/)**, providing reliable fallback for DOI lookups.
- **[DataCite API](https://support.datacite.org/docs/api)**: Used for verifying Zenodo and other repository-hosted DOIs.
- **[arXiv API](https://arxiv.org/help/api)**: Used for direct verification of pre-print identifiers.
- **[python-dotenv](https://github.com/theskumar/python-dotenv)**: For managing environment variables securely.
- **[Requests](https://requests.readthedocs.io/)**: To handle all API communications.
- **[beautifulsoup4](https://www.beautifulsoup.com/)**: For parsing HTML content during web fallback.
- **[duckduckgo-search (ddgs)](https://pypi.org/project/duckduckgo-search/)**: For performing privacy-respecting web searches without an API key.
- **URL Extraction**: Enhanced reference parsing to extract and utilize direct URLs (e.g., DOIs, arXiv IDs) found in the original text before resorting to web search.
- **Partial ARXIV Identifiers**: Added support for extracting arXiv IDs from partial identifiers in reference text (e.g., "arXiv:2403.02221" or "CoRR, abs/1810.04805").
