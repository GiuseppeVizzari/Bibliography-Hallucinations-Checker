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

## How It Works

The app performs a multi-stage verification process to ensure references in your PDF are legitimate and not "hallucinations".

1. **Extraction**: The app parses your PDF to find the bibliography section. It uses advanced regex to extract DOIs and arXiv IDs even from complex layouts.
2. **DOI Healing**: If a DOI appears broken (e.g., split by a line break or space in the PDF), the app attempts to "heal" it by testing potential reconstructions against known databases.
3. **Verification**: 
   - **DOI-First**: If a DOI is detected, the app attempts lookups in **OpenAlex**, **Crossref**, and **DataCite** (for Zenodo/repository DOIs).
   - **arXiv Support**: Direct verification for arXiv pre-prints using the official API.
   - **Title Fallback**: If no identifiers are found, it performs a search in **OpenAlex** using the extracted title.
4. **Similarity Checking**: Every found result is compared against the original text extracted from the PDF using a string similarity algorithm (`difflib`).

## Features
- ✅ **Hallucination Detection**: Visual cues (badges and row highlighting) alert you when a found reference significantly differs from the PDF text.
- ✅ **DOI Healing**: Automatically fixes broken DOIs caused by PDF formatting.
- ✅ **Multi-Engine Search**: OpenAlex, Crossref, DataCite, and arXiv support.
- ✅ **Detailed Metadata**: Extracts Title, Authors, Year, and Venue for verification.
- ✅ **Modern UI**: Clean, responsive dashboard for viewing analysis results.
- ✅ **No API Keys Required**: Uses open scholarly APIs.

## Understanding Results

- **Similarity Badge**: 
    - <span style="color:green">**High (>80%)**</span>: Strong match.
    - <span style="color:orange">**Moderate (60-80%)**</span>: Likely the correct paper, but check for metadata mismatches.
    - <span style="color:red">**Low (<60%)**</span>: Potential hallucination or incorrect match. The row will be highlighted and show a **"Check Match"** status.

## Troubleshooting

### "No references found"
- PDF might use non-standard section headers (the app looks for "References", "Bibliography", etc.)
- Try a different PDF or check the layout manually.

### Port 5000 in Use (macOS)
- If you see "Address already in use", disable **'AirPlay Receiver'** in System Settings -> General -> AirDrop & Handoff, as it often occupies port 5000.

## Acknowledgments

This project is built using several powerful open-source libraries and APIs:

- **[PyMuPDF (fitz)](https://github.com/pymupdf/PyMuPDF)**: For extracting text and metadata from PDF documents.
- **[Flask](https://flask.palletsprojects.com/)**: To provide the web-based user interface and application routing.
- **[pyalex](https://github.com/jperkel/pyalex)**: The Python client for the **[OpenAlex API](https://openalex.org/)**, used for high-speed scholarly work verification.
- **[habanero](https://github.com/sckott/habanero)**: A low-level client for the **[Crossref API](https://www.crossref.org/)**, providing reliable fallback for DOI lookups.
- **[DataCite API](https://support.datacite.org/docs/api)**: Used for verifying Zenodo and other repository-hosted DOIs.
- **[arXiv API](https://arxiv.org/help/api)**: Used for direct verification of pre-print identifiers.
- **[python-dotenv](https://github.com/theskumar/python-dotenv)**: For managing environment variables securely.
- **[Requests](https://requests.readthedocs.io/)**: To handle all API communications.
