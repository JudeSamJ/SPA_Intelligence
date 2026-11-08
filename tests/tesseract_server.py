"""TEST-ONLY stand-in for a Qwen vision endpoint: an OpenAI-compatible /chat/completions server that does REAL OCR with Tesseract on
the page image it receives and answers in the JSON shape the app asks for (lines with pixel bounding boxes).

It is not Qwen. It exists so the whole path (page rendering, HTTP, reply parsing, coordinate scaling, text layer, grounding, evidence)
can be exercised with genuine OCR output, including its real recognition errors."""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AVAILABLE = shutil.which("tesseract") is not None


def ocr_lines(png: bytes) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "p.png"
        f.write_bytes(png)
        tsv = subprocess.run(["tesseract", str(f), "stdout", "--psm", "4", "tsv"], capture_output=True, text=True, timeout=120,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"}).stdout       # parallel pages: one thread each
    rows: dict[tuple, list] = {}
    for ln in tsv.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) < 12 or c[0] != "5" or not c[11].strip() or float(c[10]) < 0:
            continue
        key = (c[2], c[3], c[4])
        l, t, w, h = int(c[6]), int(c[7]), int(c[8]), int(c[9])
        rows.setdefault(key, []).append((l, t, l + w, t + h, c[11].strip()))
    out = []
    for words in rows.values():
        out.append({"text": " ".join(w[4] for w in words),
                    "bbox": [min(w[0] for w in words), min(w[1] for w in words), max(w[2] for w in words), max(w[3] for w in words)]})
    return sorted(out, key=lambda x: (x["bbox"][1], x["bbox"][0]))


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.server.seen.append({"auth": self.headers.get("Authorization"), "model": body.get("model")})
        uri = body["messages"][0]["content"][1]["image_url"]["url"]
        lines = ocr_lines(base64.b64decode(uri.split(",", 1)[1]))
        data = json.dumps({"choices": [{"message": {"content": "```json\n" + json.dumps({"lines": lines}) + "\n```"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start() -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    srv.seen = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"
