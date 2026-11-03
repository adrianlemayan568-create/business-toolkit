"""Production WSGI entry point for Gunicorn."""

from app import app

application = app
