"""Gunicorn entry point: `gunicorn wsgi:app` (see render.yaml)."""
import logging

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app({"DASH_SNAPSHOT_THREAD": True})      # the midnight snapshot runs in the one server process
