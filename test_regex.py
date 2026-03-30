import re

texts = [
    '[36] F. Solera, S. Calderara, and R. Cucchiara, “Structured learning for detection of social groups in crowd,” in 2015 IEEE',
    '[1] A. Einstein, ``On the Electrodynamics of Moving Bodies\'\', Annalen der Physik, 1905',
    '[2] "Title of the paper", Journal, 2020',
    '3. Someone, ``Something else", etc.'
]

def extract(ref_text):
    text = re.sub(r'^\s*\[?\d+\]?\.\?\s*', '', ref_text)
    
    # Try to find text in quotes
    quoted = re.search(r'["“`\'][`\'"]*([^"”\']+)["”\']+', text)
    if quoted:
        return quoted.group(1).strip()
    return None

for t in texts:
    print(extract(t))

