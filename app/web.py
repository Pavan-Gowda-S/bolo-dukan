"""A very small web framework on Python's standard library (no compiled packages).

Routes look like  @app.route("POST", "/api/session/{session_id:int}/orders")
and handlers receive (req, **params) and return a dict/list (sent as JSON) or a Response.
"""
import json
import os
import mimetypes
import re
import sys
import time
import traceback
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY = 20 * 1024 * 1024

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("text/csv", ".csv")


class HTTPError(Exception):
    def __init__(self, status: int, detail: str = ""):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def parse_cookies(header: str) -> dict:
    """Forgiving Cookie-header parser.

    Browsers send every cookie for the host, and on localhost that includes cookies from other apps on
    other ports. http.cookies.SimpleCookie stops at the first cookie it dislikes (JSON, spaces,
    brackets), which silently dropped our login cookie. Split on ';' and keep whatever parses.
    """
    out: dict[str, str] = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if not sep or not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        out.setdefault(name.strip(), value)  # first one wins, like browsers' most-specific-path order
    return out


class UploadedFile:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self.data = data


class Request:
    def __init__(self, method: str, target: str, headers, body: bytes, client_ip: str):
        parts = urlsplit(target)
        self.method = method
        self.path = unquote(parts.path) or "/"
        self.query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.headers = headers
        self.body = body
        self.client_ip = client_ip
        self.cookie_header = headers.get("Cookie") or ""
        self.cookies = parse_cookies(self.cookie_header)
        self._form = None

    def cookie_all(self, name: str) -> list[str]:
        """Every value sent for this cookie name (several apps on localhost may share a name)."""
        vals = []
        for part in self.cookie_header.split(";"):
            n, sep, v = part.strip().partition("=")
            if sep and n.strip() == name:
                vals.append(v.strip().strip('"'))
        return vals

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    @property
    def base_url(self) -> str:
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "localhost:8000"
        proto = self.headers.get("X-Forwarded-Proto") or "http"
        return f"{proto}://{host}"

    def json(self) -> dict:
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HTTPError(400, "Invalid JSON")
        if not isinstance(data, dict):
            raise HTTPError(400, "Expected a JSON object")
        return data

    def form(self) -> tuple[dict, dict]:
        """multipart/form-data -> (fields, files)"""
        if self._form is not None:
            return self._form
        ctype = self.headers.get("Content-Type") or ""
        fields: dict[str, str] = {}
        files: dict[str, UploadedFile] = {}
        if ctype.startswith("multipart/form-data"):
            raw = b"Content-Type: " + ctype.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + self.body
            msg = BytesParser(policy=policy.default).parsebytes(raw)
            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                payload = part.get_payload(decode=True) or b""
                filename = part.get_filename()
                if filename is not None:
                    files[name] = UploadedFile(filename, part.get_content_type(), payload)
                else:
                    fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        elif ctype.startswith("application/x-www-form-urlencoded"):
            fields = {k: v[0] for k, v in parse_qs(self.body.decode("utf-8", errors="replace")).items()}
        self._form = (fields, files)
        return self._form


def _secure_cookies() -> bool:
    """True when PUBLIC_URL is an https:// address (the deployed site). Local http://localhost keeps working without it."""
    return os.getenv("PUBLIC_URL", "").strip().lower().startswith("https://")


class Response:
    def __init__(self, body: bytes | str = b"", status: int = 200, content_type: str = "text/plain; charset=utf-8",
                 headers: dict | None = None):
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status
        self.content_type = content_type
        self.headers = dict(headers or {})
        self.cookies: list[str] = []

    def set_cookie(self, name: str, value: str, max_age: int | None = None, httponly: bool = True, samesite: str = "Lax"):
        c = f"{name}={value}; Path=/; SameSite={samesite}"
        if max_age is not None:
            c += f"; Max-Age={max_age}"
        if httponly:
            c += "; HttpOnly"
        if _secure_cookies():  # live site on HTTPS: the browser never sends the login cookie over plain http
            c += "; Secure"
        self.cookies.append(c)

    def delete_cookie(self, name: str):
        self.cookies.append(f"{name}=; Path=/; Max-Age=0; SameSite=Lax")


# Changes every time the server starts, so open pages can notice new code and reload themselves.
BUILD = format(time.time_ns(), "x")


def json_response(data, status: int = 200) -> Response:
    return Response(json.dumps(data, ensure_ascii=False, default=str), status, "application/json; charset=utf-8",
                    {"Cache-Control": "no-store", "X-App-Build": BUILD})


class App:
    def __init__(self, static_dir: Path):
        self.routes: list[tuple[str, re.Pattern, dict, callable]] = []
        self.static_dir = static_dir.resolve()

    def route(self, method: str, pattern: str):
        converters = {}

        def repl(m):
            name, kind = m.group(1), m.group(2) or "str"
            converters[name] = int if kind == "int" else str
            return rf"(?P<{name}>\d+)" if kind == "int" else rf"(?P<{name}>[^/]+)"

        regex = re.compile("^" + re.sub(r"\{(\w+)(?::(\w+))?\}", repl, pattern) + "$")

        def deco(fn):
            self.routes.append((method, regex, converters, fn))
            return fn

        return deco

    def _static(self, req: Request) -> Response:
        rel = req.path[len("/static/"):]
        target = (self.static_dir / rel).resolve()
        if self.static_dir not in target.parents or not target.is_file():
            raise HTTPError(404, "Not found")
        return file_response(target, cache="no-cache")  # always fresh after you edit a file

    def dispatch(self, req: Request) -> Response:
        if req.path.startswith("/static/") and req.method in ("GET", "HEAD"):
            return self._static(req)
        allowed = False
        for method, regex, converters, fn in self.routes:
            m = regex.match(req.path)
            if not m:
                continue
            if method != req.method and not (method == "GET" and req.method == "HEAD"):
                allowed = True
                continue
            params = {k: converters[k](v) for k, v in m.groupdict().items()}
            result = fn(req, **params)
            if isinstance(result, Response):
                return result
            return json_response(result if result is not None else {"ok": True})
        if allowed:
            raise HTTPError(405, "Method not allowed")
        raise HTTPError(404, "Not found")


def file_response(path: Path, cache: str = "no-cache", content_type: str | None = None) -> Response:
    ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"):
        ctype += "; charset=utf-8"
    return Response(path.read_bytes(), 200, ctype, {"Cache-Control": cache})


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "BoloDukaan/1.0"

        def _handle(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_BODY:
                self._send(json_response({"detail": "Upload is too big"}, 413))
                self.close_connection = True
                return
            body = self.rfile.read(length) if length else b""
            fwd = self.headers.get("X-Forwarded-For")
            ip = fwd.split(",")[0].strip() if fwd else self.client_address[0]
            req = Request(self.command, self.path, self.headers, body, ip)
            try:
                resp = app.dispatch(req)
            except HTTPError as e:
                resp = json_response({"detail": e.detail}, e.status)
            except Exception:
                traceback.print_exc()
                resp = json_response({"detail": "Server error. Check the server window for details."}, 500)
            self._send(resp, head=self.command == "HEAD")

        def _send(self, resp: Response, head: bool = False):
            try:
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.content_type)
                self.send_header("Content-Length", str(len(resp.body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                for k, v in resp.headers.items():
                    self.send_header(k, v)
                for c in resp.cookies:
                    self.send_header("Set-Cookie", c)
                self.end_headers()
                if not head:
                    self.wfile.write(resp.body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _handle

        def log_message(self, fmt, *args):
            # Keep the console readable: skip the 2-second polling noise.
            line = fmt % args
            if "/api/dashboard" in line or "/api/session/" in line and '" 200' in line and "GET" in line:
                return
            if "/static/" in line and '" 200' in line:
                return
            sys.stderr.write(f"  {self.address_string()} {line}\n")

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # on Windows, True would let two servers share the port


def serve(app: App, host: str, port: int) -> None:
    httpd = Server((host, port), make_handler(app))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        httpd.server_close()
