import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pdf_processor import extract_bibliography

# Let's mock a case where references end and we have a trailing biography
# We can just write a quick test on the new split logic.
# Wait, let's test if the updated extract_bibliography functions correctly or run the test suite.

# Let's run the existing test suite using pytest to ensure no regressions.
import subprocess
try:
    res = subprocess.run([".venv/bin/pytest"], capture_output=True, text=True)
    print("Pytest stdout:")
    print(res.stdout)
    print("Pytest stderr:")
    print(res.stderr)
except Exception as e:
    print("Error running pytest:", e)
