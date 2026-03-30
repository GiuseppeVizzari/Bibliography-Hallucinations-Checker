import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.curdir))

from app.checkers.extraction import extract_title_from_reference

def test():
    ref = '[1] Y. Gu, B. Seanor, G. Campa, M. R. Napolitano, L. Rowe, S. Gururajan, and S. Wan, “Design and flight testing evaluation of formation control laws,” IEEE Transactions on Control Systems Technology, vol. 14, no. 6, pp. 1105–1112, 2006.'
    extracted = extract_title_from_reference(ref)
    print(f"Test 1 (Curly Quotes):|{extracted}|")
    
    ref2 = '[36] F. Solera, S. Calderara, and R. Cucchiara, ``Structured learning for detection of social groups in crowd,\'\', in 2015 IEEE'
    extracted2 = extract_title_from_reference(ref2)
    print(f"Test 2 (LaTeX Quotes):|{extracted2}|")

if __name__ == "__main__":
    test()
