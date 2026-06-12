import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pdf_processor import extract_bibliography

pdf_dir = "PDF for test"
pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]

for pdf in pdf_files:
    pdf_path = os.path.join(pdf_dir, pdf)
    print(f"\n==========================================")
    print(f"Extracting bibliography from: {pdf}")
    print(f"==========================================")
    try:
        refs = extract_bibliography(pdf_path)
        print(f"Found {len(refs)} references.")
        if refs:
            print("First reference:")
            print("  ", refs[0])
            print("Last reference:")
            print("  ", refs[-1])
    except Exception as e:
        print(f"Error: {e}")
