# Bibliography Hallucinations Checker - Setup Guide

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Your Email (Optional)
The application uses **OpenAlex** for high-speed reference verification. To get even faster responses (access to the "polite pool"), you can add your email to `app/reference_checker.py`:

```python
# app/reference_checker.py line 16
pyalex.config.email = "your-email@example.com"
```

### 3. Run the Application
```bash
python run.py
```

Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

## How It Works

The app uses **OpenAlex**, a free and open index of over 250M scholarly works, with a **Crossref** fallback for DOI-based verification.

1. **Extraction**: The app parses your PDF to find the bibliography section. It also attempts to extract DOIs from the reference text.
2. **Verification**: 
   - **DOI-First**: If a DOI is detected in the reference text, the app first attempts a direct lookup in **OpenAlex**, followed by **Crossref** or **DataCite** if needed.
   - **DataCite Support**: Added specialized support for Zenodo DOIs via the DataCite API.
   - **arXiv Support**: Direct verification for arXiv pre-prints using the official arXiv API.
   - **Title Fallback**: If no DOI/arXiv ID is found or lookups fail, the app performs a high-quality title search in **OpenAlex**.
3. **Speed**: Both OpenAlex and Crossref are fast and open, allowing for verification without artificial delays.

## Features
- ✅ Automatic PDF bibliography extraction
- ✅ Two-column PDF support
- ✅ High-speed verification via OpenAlex API
- ✅ Reliable fallback via Crossref for references with DOIs
- ✅ No API keys required
- ✅ Detailed metadata extraction (Title, Authors, Year, Venue)
- ✅ Direct links to papers via DOI or OpenAlex

## Troubleshooting

### "No references found"
- PDF might use non-standard section headers (the app looks for "References", "Bibliography", etc.)
- Try a different PDF or check the layout manually

### Incorrect matches
- Occasionally, short or ambiguously formatted references might return incorrect top results. Check the "Online Data" column to verify the match.
