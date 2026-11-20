"""Outgoing HTTPS calls with the standard library (urllib)."""
import json
import socket
import ssl
import urllib.error
import urllib.request

_ctx = ssl.create_default_context()  # uses the Windows certificate store


class NetError(Exception):
    """Could not reach the other server at all."""


def request(method: str, url: str, body: dict | None = None, headers: dict | None = None,
            timeout: float = 20) -> tuple[int, object]:
    """Returns (status, parsed JSON or text). Raises NetError on connection problems."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "BoloDukaan/1.0"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
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
