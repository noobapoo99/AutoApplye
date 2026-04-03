from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer


HOST = "0.0.0.0"
PORT = 8001
HEALTH_BODY = b"OK"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/", "/health"}:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "9")
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(HEALTH_BODY)))
        self.end_headers()
        self.wfile.write(HEALTH_BODY)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
