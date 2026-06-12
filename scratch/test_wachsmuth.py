import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.checkers.extraction import extract_title_from_reference
from app.checkers.backends.openalex import lookup_by_title

ref = "D. Wachsmuth and A. Weisler. Airbnb and the rent gap: Gentrification through the sharing economy. Environment and Planning A: Economy and Space, 50(6):1147–1170, 2018."
extracted = extract_title_from_reference(ref)
print("EXTRACTED TITLE:")
print(repr(extracted))

print("\nOPENALEX LOOKUP RESULT:")
result = lookup_by_title(extracted)
print(result)
