"""Production WSGI entry point for the selected Place Twins artifact bundle."""

from .app import create_app

app = create_app()
server = app.server
