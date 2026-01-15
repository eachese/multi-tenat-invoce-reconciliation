"""ASGI shim exposing the FastAPI app under the root module.

This allows running `uvicorn main:app` from the project root.
"""

from app.main import app

__all__ = ["app"]
