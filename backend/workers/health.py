"""
Minimal HTTP health check server — stdlib only.
Starts on port 8001 in a background thread.
Called by docker-compose and Render healthchecks.
"""
import json, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # suppress access logs

def start_health_server(port: int = 8001) -> threading.Thread:
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    import time
    t = start_health_server()
    print(f"Health server running on :8001")
    while True:
        time.sleep(60)
