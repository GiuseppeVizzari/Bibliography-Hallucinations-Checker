"""WSGI entry point for production deployment (gunicorn, uWSGI, etc.)."""

from app import create_app

app = create_app()
