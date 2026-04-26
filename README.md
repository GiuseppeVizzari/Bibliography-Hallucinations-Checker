# Bibliography Hallucinations Checker - Setup Guide

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Your Email (Optional)
The application uses **OpenAlex** for high-speed reference verification. To get even faster responses (access to the "polite pool"), you can add your email to the `.env` file:

```env
OPENALEX_EMAIL=your-email@example.com
```

### 3. Run the Application
```bash
python run.py
```

Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

To capture all output to a log file for debugging:
```bash
python run.py > debug.log 2>&1
```

## How It Works

The app performs a multi-stage verification process to ensure references in your PDF are legitimate and not "hallucinations".

1. **Bibliography Detection**: The app parses your PDF to locate the bibliography section. It recognises a broad set of section headers, including English (`References`, `Bibliography`, `Works Cited`), Italian (`Bibliografia`, `Riferimenti`), and common typos (`Rererences`). Once found, it collects only the content up to the next section boundary (appendix, acknowledgements, etc.) and ignores the rest.
2. **Appendix Skipping**: After the bibliography, common section headers (Appendix, Annex, Supplementary Material, and Italian equivalents such as *Appendice*, *Ringraziamenti*) act as hard stop points. Appendix table/figure captions (`Table A1`, `Fig. A2`) and pure numeric table rows are also filtered out to prevent false positives.
3. **Reference Splitting**: The app automatically detects the citation style in use:
   - **Bracketed numbers** – `[1]`, `[2]`, … (IEEE / Vancouver)
   - **Plain numbers** – `1.`, `2.`, … (numbered lists)
   - **Block-based** – one paragraph per reference, as used by APA, Chicago, and similar author–date styles
4. **Identifier Extraction & Healing**: DOIs, arXiv IDs, and bare URLs are extracted from each reference. If a DOI has been split by a line break or space in the PDF (e.g. `10.3390/ fi15010012`), the app attempts to reconstruct and validate it automatically.
5. **Verification**:
   - **DOI-First**: Lookups in **OpenAlex**, **Crossref**, and **DataCite** (for Zenodo/repository DOIs).
   - **arXiv Support**: Direct verification for arXiv pre-prints using the official API.
   - **Title Fallback**: When no identifier is found, a full-text search in **OpenAlex** is performed using the extracted title. The title extractor handles quoted titles, author-year formats (APA/Chicago), and comma-delimited styles, while rejecting false positives such as page-number ranges or DOI strings.
6. **Similarity Checking**: Every found result is compared against the original reference text using a string-similarity algorithm (`difflib`), so a wrong-paper match is visually flagged even when the lookup technically succeeds.

## Features

- ✅ **Hallucination Detection**: Visual cues (badges and row highlighting) flag found references that differ significantly from the PDF text.
- ✅ **Multi-language Bibliography Headers**: Supports English and Italian section titles, plus common OCR/typo variants.
- ✅ **Appendix Termination**: Automatically stops collecting references when it encounters appendix or acknowledgement sections, including lettered appendix tables (`Table A1`) and numeric table rows.
- ✅ **DOI Healing**: Automatically fixes broken DOIs caused by PDF line-wrapping or spaces.
- ✅ **Multi-Engine Search**: OpenAlex, Crossref, DataCite, and arXiv support.
- ✅ **Clickable Links in Results**: Both the original reference column (DOI / arXiv / URL) and the found paper column (title link + source link) provide direct hyperlinks.
- ✅ **Back-to-Top Button**: A floating button appears while scrolling the results page for quick navigation.
- ✅ **Detailed Metadata**: Extracts Title, Authors, Year, and Venue for each verified reference.
- ✅ **No API Keys Required**: Uses open scholarly APIs.

## Understanding Results

| Similarity | Meaning |
|---|---|
| **≥ 80%** 🟢 | Strong match — very likely the correct paper. |
| **60–80%** 🟡 | Moderate match — probably correct, but worth a manual check. |
| **< 60%** 🔴 | Low match — potential hallucination or wrong paper returned. Row is highlighted and shows a **"Check Match"** badge. |

### Result Table Columns

- **Extracted Reference** — raw text pulled from the PDF. A 🔗 **Source** badge appears below when a DOI, arXiv ID, or URL was found in the original text.
- **Status** — `Found`, `Check Match`, `Not Found`, `Skipped`, or `Error`.
- **Source** — which API resolved the reference (OpenAlex, Crossref, DataCite, arXiv).
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
