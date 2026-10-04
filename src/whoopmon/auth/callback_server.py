"""One-shot local HTTP server that receives the OAuth redirect."""

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

_PAGE = (
    "<html><body style='font-family:system-ui;padding:40px'>"
    "<h2>{title}</h2><p>{body}</p></body></html>"
)


@dataclass
class CallbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None


def wait_for_callback(host: str, port: int, path: str, timeout: float = 300) -> CallbackResult:
    result = CallbackResult()
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib name
            url = urlparse(self.path)
            if url.path != path:
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(url.query)
            result.code = qs.get("code", [None])[0]
            result.state = qs.get("state", [None])[0]
            result.error = qs.get("error", [None])[0]
            ok = result.code is not None and result.error is None
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            page = _PAGE.format(
                title="WHOOP connected" if ok else "WHOOP login failed",
                body="You can close this tab." if ok else f"Error: {result.error}",
            )
            self.wfile.write(page.encode())
            done.set()

        def log_message(self, *_args: object) -> None:
            # The default handler prints the full URL, which holds the auth code.
            return

    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not done.wait(timeout):
            result.error = "timeout"
    finally:
        server.shutdown()
    return result
