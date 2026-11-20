"""Outgoing HTTPS calls with the standard library (urllib)."""
import json
import socket
import ssl
import urllib.error
import urllib.request
import uuid

_ctx = ssl.create_default_context()  # uses the Windows certificate store


class NetError(Exception):
    """Could not reach the other server at all."""


def request_multipart(url: str, fields: dict, files: dict, headers: dict | None = None,
                      timeout: float = 20) -> tuple[int, object]:
    """POST multipart/form-data. files = {name: (filename, content_type, bytes)}."""
    boundary = "----bolo" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        if v is None:
            continue
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + str(v).encode() + b"\r\n"
    for k, (fname, ctype, data) in files.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    hdrs = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    hdrs.update(headers or {})
    return _send(urllib.request.Request(url, data=bytes(out), method="POST",
                                        headers={"Accept": "application/json", "User-Agent": "BoloDukaan/1.0", **hdrs}),
                 timeout)


def request(method: str, url: str, body: dict | None = None, headers: dict | None = None,
            timeout: float = 20) -> tuple[int, object]:
    """Returns (status, parsed JSON or text). Raises NetError on connection problems."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "BoloDukaan/1.0"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    return _send(urllib.request.Request(url, data=data, method=method, headers=hdrs), timeout)


def _send(req: urllib.request.Request, timeout: float) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError) as e:
        raise NetError(str(getattr(e, "reason", e)))
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text) if text else {}
    except ValueError:
        return status, text
