"""Serve dist/ locally with the same headers and pretty URLs Netlify uses.

Usage: python3 scripts/serve_dist.py [port]
Lets you catch Content-Security-Policy problems before deploying.
"""

import fnmatch
import http.server
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
RULES = tomllib.loads((ROOT / "netlify.toml").read_text()).get("headers", [])


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def end_headers(self):
        path = self.path.split("?")[0]
        merged = {}
        for rule in RULES:  # later rules override earlier ones, as on Netlify
            if fnmatch.fnmatch(path, rule["for"]):
                merged.update(rule["values"])
        for name, value in merged.items():
            self.send_header(name, value)
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        if code == 404 and (DIST / "404.html").exists():
            body = (DIST / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().send_error(code, message, explain)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    print(f"Serving {DIST} on http://localhost:{port}")
    http.server.ThreadingHTTPServer(("", port), Handler).serve_forever()
