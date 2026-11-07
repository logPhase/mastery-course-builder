#!/usr/bin/env python3
"""Serve the review app: python3 server.py --data <dir>/error_discovery_data [--port 8770]

GET / is the app. GET /api/<name> returns <name>.json from the data folder; POST /api/<name> replaces it
(samples, annotations, patterns) or, for suggestions, upserts by id. Binds 127.0.0.1 only; writes are atomic."""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from prepare import merge_suggestions, read_json, write_json

HERE = Path(__file__).resolve().parent
FILES = {f"/api/{n}": f"{n}.json" for n in ("samples", "annotations", "graph", "patterns", "suggestions")}
WRITABLE = {"samples.json": dict, "annotations.json": list, "patterns.json": dict, "suggestions.json": (list, dict)}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    data = Path(".")

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.local_host():
            return self.send_error(403)
        if path in ("/", "/index.html"):
            return self.send_file(HERE / "index.html", "text/html; charset=utf-8")
        if path in FILES:
            return self.send_file(self.data / FILES[path], "application/json")
        self.send_error(404)

    def do_POST(self):
        name = FILES.get(urlsplit(self.path).path)
        if name not in WRITABLE:
            return self.send_error(404)
        # a JSON content type forces a CORS preflight, which this server never answers: other sites cannot write here
        if not self.local_host() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send_error(403)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        except ValueError:
            return self.send_error(400, "body is not JSON")
        ok = isinstance(body, WRITABLE[name])
        if name == "samples.json":
            ok = ok and isinstance(body.get("records"), list) and isinstance(body.get("sample"), list)
        if name == "annotations.json":
            ok = ok and all(isinstance(a, dict) and a.get("id") and a.get("record_id") for a in body)
        if not ok:
            return self.send_error(400, f"wrong shape for {name}")
        with LOCK:
            if name == "suggestions.json":
                body = merge_suggestions(read_json(self.data / name, []), body if isinstance(body, list) else [body])
            write_json(self.data / name, body)
        self.send_body(200, json.dumps({"ok": True, "count": len(body)}).encode(), "application/json")

    def local_host(self):  # a DNS-rebinding page would arrive under its own host name
        return self.headers.get("Host", "").rsplit(":", 1)[0] in ("127.0.0.1", "localhost")

    def send_file(self, path, ctype):
        try:
            st = path.stat()
            body = path.read_bytes()
        except FileNotFoundError:
            return self.send_error(404)
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'  # the app polls; an unchanged file costs a 304
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            return self.end_headers()
        self.send_body(200, body, ctype, etag)

    def send_body(self, code, body, ctype, etag=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code="-", size="-"):
        pass  # the app polls every few seconds; errors still go to stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="the error_discovery_data folder prepare.py wrote")
    ap.add_argument("--port", type=int, default=8770, help="0 picks a free port")
    a = ap.parse_args()
    Handler.data = Path(a.data).resolve()
    if not (Handler.data / "samples.json").exists():
        raise SystemExit(f"{Handler.data}/samples.json is missing: run prepare.py first")
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Review app: http://127.0.0.1:{server.server_address[1]}/  (data: {Handler.data})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
