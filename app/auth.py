"""Owner passwords (salted PBKDF2) and signed login cookies."""
import base64
import hashlib
import hmac
import secrets
import time

from .config import SECRET_KEY
from .db import db
from .web import HTTPError, Request

COOKIE_NAME = "bd_owner"
COOKIE_MAX_AGE = 60 * 60 * 24 * 14  # 14 days
_ITERATIONS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_owner_cookie(owner_id: int) -> str:
    payload = f"{owner_id}.{int(time.time()) + COOKIE_MAX_AGE}"
    return f"{payload}.{_sign(payload)}"


def read_owner_cookie(value: str | None) -> int | None:
    if not value:
        return None
    try:
        owner_id, expires, sig = value.split(".")
        payload = f"{owner_id}.{expires}"
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        if int(expires) < time.time():
            return None
        return int(owner_id)
    except Exception:
        return None


def require_owner(request: Request) -> dict:
    """The logged-in owner, or 401."""
    owner_id = read_owner_cookie(request.cookies.get(COOKIE_NAME))
    if owner_id is None:
        raise HTTPError(401, "Please log in")
    with db() as conn:
        owner = conn.execute(
            "SELECT o.id, o.email, o.restaurant_id, r.name AS restaurant_name, r.table_count "
            "FROM owners o JOIN restaurants r ON r.id = o.restaurant_id WHERE o.id = ?",
            (owner_id,),
        ).fetchone()
    if owner is None:
        raise HTTPError(401, "Please log in")
    return dict(owner)
