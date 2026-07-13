# app/checkers/backends/__init__.py

from .openalex import OpenAlexBackend
from .crossref import CrossrefBackend
from .datacite import DataCiteBackend
from .arxiv import ArxivBackend
from .url_checker import URLCheckerBackend
from .web_fallback import WebFallbackBackend
from .dblp import DBLPBackend

__all__ = [
    "OpenAlexBackend",
    "CrossrefBackend",
    "DataCiteBackend",
    "ArxivBackend",
    "URLCheckerBackend",
    "WebFallbackBackend",
    "DBLPBackend",
]