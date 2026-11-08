"""Tiny stand-in for Supabase Auth, for browser checks only."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

USERS = {"boss@co.com": "u-boss", "rita@co.com": "u-rita", "bella@buyer.com": "u-bella", "sam@co.com": "u-sam"}
PW = "correct-horse-battery"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if self.path.startswith("/auth/v1/token"):
            e = body.get("email")
            if e in USERS and body.get("password") == PW:
                return self._send(200, {"access_token": "x", "user": {"id": USERS[e], "email": e, "email_confirmed_at": "2026-01-01T00:00:00Z", "user_metadata": {"full_name": e.split("@")[0].title()}}})
            return self._send(400, {"error_code": "invalid_credentials"})
        if self.path.startswith("/auth/v1/signup") or self.path.startswith("/auth/v1/recover"):
            return self._send(200, {})
        self._send(404, {})

    def do_PUT(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        self._send(200, {"id": "x"} if self.headers.get("Authorization") == "Bearer good-token-123456" else {"error_code": "bad_jwt"})


HTTPServer(("127.0.0.1", 9999), H).serve_forever()
