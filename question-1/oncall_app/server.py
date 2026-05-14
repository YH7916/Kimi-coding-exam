"""HTTP server adapter for the route layer."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import cast

from oncall_app.repository import DocumentRepository
from oncall_app.routes import Router


class OnCallHTTPServer(HTTPServer):
    """HTTPServer carrying the application router."""

    def __init__(self, server_address, request_handler_class, router: Router):
        super().__init__(server_address, request_handler_class)
        self.router = router


class RequestHandler(BaseHTTPRequestHandler):
    """Translate BaseHTTPRequestHandler callbacks into router calls."""

    server_version = "OnCallAssistant/0.1"

    def do_GET(self):  # pylint: disable=invalid-name
        """Handle GET requests."""
        self._handle_request()

    def do_POST(self):  # pylint: disable=invalid-name
        """Handle POST requests."""
        self._handle_request()

    def _handle_request(self):
        """Read the request body, route, and write the response."""
        body_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(body_length) if body_length else b""
        server = cast(OnCallHTTPServer, self.server)
        response = server.router.handle(self.command, self.path, body)
        response_body = response.body.encode("utf-8")

        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format, *args):  # pylint: disable=redefined-builtin
        """Silence default request logging for cleaner interview demos."""


def run_server(data_dir: Path, host: str = "127.0.0.1", port: int = 8000):
    """Start the blocking HTTP server."""
    repository = DocumentRepository(data_dir)
    router = Router(repository)
    server = OnCallHTTPServer((host, port), RequestHandler, router)
    print(f"On-Call Assistant running at http://{host}:{port}")
    server.serve_forever()
