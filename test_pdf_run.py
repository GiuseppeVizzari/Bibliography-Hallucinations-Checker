from app.pdf_processor import extract_bibliography
from app.checkers.orchestrator import check_reference

pdf_path = 'PDF for test/DSLSC_Castelnovo_Yzeiri.pdf'
print(f"Extracting bibliography from {pdf_path}...")
refs = extract_bibliography(pdf_path)
print(f"Found {len(refs)} references.\n")

for i, ref in enumerate(refs):
    print(f"--- Reference {i+1} ---")
    result = check_reference(ref)
    print(f"Result: {result}\n")
