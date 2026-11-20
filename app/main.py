"""Bolo Dukaan for Restaurants: the backend.

Run:  python run.py        (or double-click start.bat)
"""
import csv
import io
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import qrcode
import qrcode.image.svg

from . import cashfree, config, gemini
from .auth import COOKIE_MAX_AGE, COOKIE_NAME, hash_password, make_owner_cookie, require_owner, verify_password
from .db import (
    ACCEPTED, ACTIVE_SESSION_STATUSES, BILL_REQUESTED, BILLABLE_ORDER_STATUSES, CLOSED, OPEN, ORDER_REJECTED,
    PAID, PAID_CASH, PENDING, PREPARING, REJECTED, SERVED, WAITING_APPROVAL, db, now_iso, row, rows,
)
from .net import NetError, request as http_request
from .web import App, HTTPError, Request, Response, file_response, json_response

IST = timezone(timedelta(hours=5, minutes=30))
LANGUAGES = {"kn-IN": "Kannada", "hi-IN": "Hindi", "en-IN": "English"}
MAX_TABLES = 60

app = App(config.STATIC_DIR)
route = app.route


# ===================================================================== validation helpers

def _str(d: dict, key: str, lo: int = 0, hi: int = 200, label: str | None = None, default: str = "") -> str:
    v = d.get(key, default)
    v = "" if v is None else str(v).strip()
    name = label or key.replace("_", " ")
    if len(v) < lo:
        raise HTTPError(400, f"Please enter {name}" if lo <= 1 else f"{name.capitalize()} must be at least {lo} characters")
    if len(v) > hi:
        raise HTTPError(400, f"{name.capitalize()} is too long (max {hi})")
    return v


def _int(d: dict, key: str, lo: int, hi: int, label: str | None = None) -> int:
    name = label or key.replace("_", " ")
    try:
        v = int(d.get(key))
    except (TypeError, ValueError):
        raise HTTPError(400, f"Please enter a number for {name}")
    if not lo <= v <= hi:
        raise HTTPError(400, f"{name.capitalize()} must be between {lo} and {hi}")
    return v


def _menu_item_in(d: dict) -> dict:
    try:
        price = int(d.get("price_paise"))
    except (TypeError, ValueError):
        raise HTTPError(400, "Please enter a price")
    if not 100 <= price <= 10_000_000:
        raise HTTPError(400, "Price must be between ₹1 and ₹1,00,000")
    return {
        "name": _str(d, "name", 1, 80, "a dish name"),
        "name_local": _str(d, "name_local", 0, 80),
        "category": _str(d, "category", 0, 40) or "Menu",
        "price_paise": price,
        "available": 1 if d.get("available", True) not in (False, 0, "0", "false") else 0,
        "photo_url": _str(d, "photo_url", 0, 500),
    }


# ===================================================================== helpers

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "restaurant"


_ngrok_cache = {"url": None, "at": 0.0}


def _ngrok_url() -> str | None:
    if time.time() - _ngrok_cache["at"] < 15:
        return _ngrok_cache["url"]
    url = None
    try:
        _, data = http_request("GET", "http://127.0.0.1:4040/api/tunnels", timeout=0.8)
        for tunnel in (data or {}).get("tunnels", []) if isinstance(data, dict) else []:
            if str(tunnel.get("public_url", "")).startswith("https://"):
                url = tunnel["public_url"].rstrip("/")
                break
    except (NetError, Exception):
        url = None
    _ngrok_cache.update(url=url, at=time.time())
    return url


def public_base(req: Request) -> str:
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    return _ngrok_url() or req.base_url


def _bill_paise(conn, session_id: int) -> int:
    return int(conn.execute(
        "SELECT COALESCE(SUM(oi.qty * oi.unit_price_paise), 0) FROM order_items oi "
        "JOIN orders o ON o.id = oi.order_id WHERE o.session_id = ? AND o.status IN (?, ?, ?)",
        (session_id, *BILLABLE_ORDER_STATUSES),
    ).fetchone()[0])


def _orders_with_items(conn, session_id: int) -> list[dict]:
    orders = rows(conn.execute("SELECT * FROM orders WHERE session_id = ? ORDER BY id", (session_id,)))
    if not orders:
        return []
    ids = [o["id"] for o in orders]
    items = rows(conn.execute(
        f"SELECT * FROM order_items WHERE order_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids
    ))
    by_order: dict[int, list] = {}
    for it in items:
        by_order.setdefault(it["order_id"], []).append({
            "name": it["name"], "qty": it["qty"], "unit_price_paise": it["unit_price_paise"],
            "menu_item_id": it["menu_item_id"],
        })
    for o in orders:
        o["items"] = by_order.get(o["id"], [])
        o["total_paise"] = sum(i["qty"] * i["unit_price_paise"] for i in o["items"])
    return orders


def _active_session(conn, table_id: int):
    marks = ",".join("?" * len(ACTIVE_SESSION_STATUSES))
    return row(conn.execute(
        f"SELECT * FROM table_sessions WHERE table_id = ? AND status IN ({marks}) ORDER BY id DESC LIMIT 1",
        (table_id, *ACTIVE_SESSION_STATUSES),
    ).fetchone())


def _table_by_token(conn, token: str) -> dict:
    t = row(conn.execute(
        "SELECT t.*, r.name AS restaurant_name, r.language, r.wifi_name, r.wifi_password "
        "FROM tables t JOIN restaurants r ON r.id = t.restaurant_id WHERE t.token = ? AND t.active = 1",
        (token,),
    ).fetchone())
    if t is None:
        raise HTTPError(404, "This QR code is not valid any more. Please ask the staff.")
    return t


def _guest_session(conn, session_id: int, req: Request) -> dict:
    """The session, if this phone belongs to it."""
    token = req.header("X-Guest-Token")
    if not token:
        raise HTTPError(401, "Please scan the table QR again.")
    s = row(conn.execute(
        "SELECT s.*, t.number AS table_number, t.restaurant_id, t.token AS table_token "
        "FROM table_sessions s JOIN session_guests g ON g.session_id = s.id "
        "JOIN tables t ON t.id = s.table_id WHERE s.id = ? AND g.token = ?",
        (session_id, token),
    ).fetchone())
    if s is None:
        raise HTTPError(401, "Please scan the table QR again.")
    return s


def _owner_session(conn, session_id: int, owner: dict) -> dict:
    s = row(conn.execute(
        "SELECT s.*, t.number AS table_number, t.restaurant_id FROM table_sessions s "
        "JOIN tables t ON t.id = s.table_id WHERE s.id = ?",
        (session_id,),
    ).fetchone())
    if s is None or s["restaurant_id"] != owner["restaurant_id"]:
        raise HTTPError(404, "Table session not found")
    return s


def _menu(conn, restaurant_id: int, only_available: bool = False) -> list[dict]:
    q = ("SELECT id, name, name_local, category, price_paise, available, photo_url FROM menu_items "
         "WHERE restaurant_id = ? AND deleted = 0")
    if only_available:
        q += " AND available = 1"
    return rows(conn.execute(q + " ORDER BY category COLLATE NOCASE, id", (restaurant_id,)))


def _new_guest(conn, session_id: int, device_id: str) -> str:
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO session_guests (session_id, token, device_id, created_at) VALUES (?, ?, ?, ?)",
        (session_id, token, device_id[:64], now_iso()),
    )
    return token


def _latest_payment(conn, session_id: int):
    return row(conn.execute(
        "SELECT * FROM payments WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,)
    ).fetchone())


def _session_view(conn, s: dict) -> dict:
    """What a guest phone sees."""
    pay = _latest_payment(conn, s["id"])
    guests = conn.execute("SELECT COUNT(*) FROM session_guests WHERE session_id = ?", (s["id"],)).fetchone()[0]
    calls = conn.execute("SELECT COUNT(*) FROM waiter_calls WHERE session_id = ? AND done = 0", (s["id"],)).fetchone()[0]
    return {
        "id": s["id"],
        "status": s["status"],
        "table_number": s["table_number"],
        "table_token": s.get("table_token"),
        "join_code": s["join_code"] if s["status"] in (OPEN, BILL_REQUESTED, PAID) else None,
        "orders": _orders_with_items(conn, s["id"]),
        "bill_paise": _bill_paise(conn, s["id"]),
        "settled_paise": s.get("settled_paise", 0),
        "pay_method": s.get("pay_method", ""),
        "guests": guests,
        "waiter_called": calls > 0,
        "payment": {"status": pay["status"], "amount_paise": pay["amount_paise"]} if pay else None,
    }


# ===================================================================== pages

PAGES = {
    "/": "index.html",
    "/owner/signup": "signup.html",
    "/owner/login": "login.html",
    "/owner/setup": "setup.html",
    "/owner/menu": "menu.html",
    "/owner/qr": "qr.html",
    "/dashboard": "dashboard.html",
    "/paid": "paid.html",
}


def _page_handler(name: str):
    def handler(req: Request):
        return file_response(config.STATIC_DIR / "pages" / name)
    return handler


for _path, _file in PAGES.items():
    route("GET", _path)(_page_handler(_file))


@route("GET", "/t/{token}")
def table_page(req: Request, token: str):
    return file_response(config.STATIC_DIR / "pages" / "table.html")


@route("GET", "/favicon.ico")
def favicon(req: Request):
    return file_response(config.STATIC_DIR / "img" / "logo.svg", cache="public, max-age=86400")


# ===================================================================== owner

def _login_response(owner_id: int, payload: dict) -> Response:
    resp = json_response(payload)
    resp.set_cookie(COOKIE_NAME, make_owner_cookie(owner_id), max_age=COOKIE_MAX_AGE)
    return resp


@route("POST", "/api/owner/signup")
def owner_signup(req: Request):
    d = req.json()
    email = _str(d, "email", 3, 120, "your email").lower()
    password = _str(d, "password", 6, 200)
    name = _str(d, "restaurant_name", 2, 80, "the restaurant name")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPError(400, "Please enter a valid email")
    with db() as conn:
        if conn.execute("SELECT 1 FROM owners WHERE email = ?", (email,)).fetchone():
            raise HTTPError(409, "An account with this email already exists. Log in instead.")
        base = _slugify(name)
        slug, n = base, 1
        while conn.execute("SELECT 1 FROM restaurants WHERE slug = ?", (slug,)).fetchone():
            n += 1
            slug = f"{base}-{n}"
        rid = conn.execute(
            "INSERT INTO restaurants (name, slug, created_at) VALUES (?, ?, ?)", (name, slug, now_iso())
        ).lastrowid
        owner_id = conn.execute(
            "INSERT INTO owners (restaurant_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (rid, email, hash_password(password), now_iso()),
        ).lastrowid
    return _login_response(owner_id, {"ok": True, "next": "/owner/setup"})


@route("POST", "/api/owner/login")
def owner_login(req: Request):
    d = req.json()
    email = str(d.get("email") or "").strip().lower()
    password = str(d.get("password") or "")
    with db() as conn:
        owner = conn.execute(
            "SELECT o.id, o.password_hash, r.table_count FROM owners o JOIN restaurants r ON r.id = o.restaurant_id "
            "WHERE o.email = ?", (email,),
        ).fetchone()
    if owner is not None and not owner["password_hash"]:
        raise HTTPError(401, "This account signs in with Google. Use the Google button.")
    if owner is None or not verify_password(password, owner["password_hash"]):
        raise HTTPError(401, "Wrong email or password")
    return _login_response(owner["id"], {"ok": True, "next": "/dashboard" if owner["table_count"] else "/owner/setup"})


@route("GET", "/api/auth/config")
def auth_config(req: Request):
    return {"google_client_id": config.GOOGLE_CLIENT_ID}


def _verify_google_token(credential: str) -> dict:
    """Ask Google to check the ID token from the Sign in with Google button, then check it was made for us."""
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPError(503, "Google sign-in isn't set up. Add GOOGLE_CLIENT_ID to .env.")
    if not credential or len(credential) > 4096:
        raise HTTPError(400, "Missing Google sign-in token")
    try:
        status, info = http_request("GET", "https://oauth2.googleapis.com/tokeninfo?id_token=" + quote(credential, safe=""),
                                    timeout=10)
    except NetError:
        raise HTTPError(504, "Could not reach Google. Check the internet and try again.")
    if status != 200 or not isinstance(info, dict):
        raise HTTPError(401, "Google sign-in failed. Please try again.")
    if info.get("aud") != config.GOOGLE_CLIENT_ID:
        raise HTTPError(401, "This Google sign-in was not made for this app.")
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPError(401, "Google sign-in failed (bad issuer).")
    try:
        if int(info.get("exp", 0)) < time.time():
            raise HTTPError(401, "Google sign-in expired. Please try again.")
    except ValueError:
        raise HTTPError(401, "Google sign-in failed.")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email") or not info.get("sub"):
        raise HTTPError(401, "Your Google email isn't verified.")
    return info


@route("POST", "/api/owner/google")
def owner_google(req: Request):
    d = req.json()
    info = _verify_google_token(str(d.get("credential") or ""))
    email, sub = str(info["email"]).lower(), str(info["sub"])
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute(
            "SELECT o.id, o.google_sub, r.table_count FROM owners o JOIN restaurants r ON r.id = o.restaurant_id "
            "WHERE o.google_sub = ? OR o.email = ? ORDER BY (o.google_sub = ?) DESC LIMIT 1", (sub, email, sub),
        ).fetchone()
        if owner is not None:
            if owner["google_sub"] != sub:  # same verified email signed up with a password before: link Google
                conn.execute("UPDATE owners SET google_sub = ? WHERE id = ?", (sub, owner["id"]))
            owner_id, nxt = owner["id"], ("/dashboard" if owner["table_count"] else "/owner/setup")
        else:
            name = _str(d, "restaurant_name", 0, 80)
            if len(name) < 2:
                first = str(info.get("given_name") or info.get("name") or "My").strip()[:40]
                name = f"{first}'s Restaurant"
            base = _slugify(name)
            slug, n = base, 1
            while conn.execute("SELECT 1 FROM restaurants WHERE slug = ?", (slug,)).fetchone():
                n += 1
                slug = f"{base}-{n}"
            rid = conn.execute("INSERT INTO restaurants (name, slug, created_at) VALUES (?, ?, ?)",
                               (name, slug, now_iso())).lastrowid
            owner_id = conn.execute(
                "INSERT INTO owners (restaurant_id, email, password_hash, google_sub, created_at) VALUES (?, ?, '', ?, ?)",
                (rid, email, sub, now_iso()),
            ).lastrowid
            nxt = "/owner/setup"
    return _login_response(owner_id, {"ok": True, "next": nxt})


@route("POST", "/api/owner/logout")
def owner_logout(req: Request):
    resp = json_response({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@route("GET", "/api/owner/me")
def owner_me(req: Request):
    owner = require_owner(req)
    with db() as conn:
        r = row(conn.execute("SELECT * FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone())
        menu_count = conn.execute(
            "SELECT COUNT(*) FROM menu_items WHERE restaurant_id = ? AND deleted = 0", (r["id"],)
        ).fetchone()[0]
    return {"email": owner["email"], "restaurant": r, "menu_count": menu_count,
            "features": config.features(), "languages": LANGUAGES}


@route("POST", "/api/owner/setup")
def owner_setup(req: Request):
    owner = require_owner(req)
    d = req.json()
    count = _int(d, "table_count", 1, MAX_TABLES, "number of tables")
    language = str(d.get("language") or "kn-IN")
    if language not in LANGUAGES:
        raise HTTPError(400, "Unknown language")
    wifi_name = _str(d, "wifi_name", 0, 60)
    wifi_password = _str(d, "wifi_password", 0, 60)
    name = _str(d, "name", 0, 80)
    rid = owner["restaurant_id"]
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = {t["number"]: t for t in rows(conn.execute("SELECT * FROM tables WHERE restaurant_id = ?", (rid,)))}
        for number, t in existing.items():
            if number > count and t["active"] and _active_session(conn, t["id"]):
                raise HTTPError(409, f"Table {number} has guests right now. Free it before removing it.")
        for number in range(1, count + 1):
            if number in existing:
                conn.execute("UPDATE tables SET active = 1 WHERE id = ?", (existing[number]["id"],))
            else:
                conn.execute("INSERT INTO tables (restaurant_id, number, token) VALUES (?, ?, ?)",
                             (rid, number, secrets.token_urlsafe(12)))
        conn.execute("UPDATE tables SET active = 0 WHERE restaurant_id = ? AND number > ?", (rid, count))
        if name:
            conn.execute("UPDATE restaurants SET name = ? WHERE id = ?", (name, rid))
        conn.execute(
            "UPDATE restaurants SET table_count = ?, language = ?, wifi_name = ?, wifi_password = ? WHERE id = ?",
            (count, language, wifi_name, wifi_password, rid),
        )
    return {"ok": True, "next": "/owner/qr"}


@route("GET", "/api/owner/menu")
def owner_menu(req: Request):
    owner = require_owner(req)
    with db() as conn:
        return {"items": _menu(conn, owner["restaurant_id"]), "features": config.features()}


@route("POST", "/api/owner/menu")
def owner_menu_add(req: Request):
    owner = require_owner(req)
    it = _menu_item_in(req.json())
    with db() as conn:
        new_id = conn.execute(
            "INSERT INTO menu_items (restaurant_id, name, name_local, category, price_paise, available, photo_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (owner["restaurant_id"], it["name"], it["name_local"], it["category"], it["price_paise"],
             it["available"], it["photo_url"]),
        ).lastrowid
    return {"ok": True, "id": new_id}


@route("PUT", "/api/owner/menu/{item_id:int}")
def owner_menu_edit(req: Request, item_id: int):
    owner = require_owner(req)
    it = _menu_item_in(req.json())
    with db() as conn:
        cur = conn.execute(
            "UPDATE menu_items SET name = ?, name_local = ?, category = ?, price_paise = ?, available = ?, photo_url = ? "
            "WHERE id = ? AND restaurant_id = ? AND deleted = 0",
            (it["name"], it["name_local"], it["category"], it["price_paise"], it["available"], it["photo_url"],
             item_id, owner["restaurant_id"]),
        )
        if cur.rowcount == 0:
            raise HTTPError(404, "Menu item not found")
    return {"ok": True}


@route("DELETE", "/api/owner/menu/{item_id:int}")
def owner_menu_delete(req: Request, item_id: int):
    owner = require_owner(req)
    with db() as conn:
        conn.execute("UPDATE menu_items SET deleted = 1 WHERE id = ? AND restaurant_id = ?",
                     (item_id, owner["restaurant_id"]))
    return {"ok": True}


@route("POST", "/api/owner/menu/bulk")
def owner_menu_bulk(req: Request):
    owner = require_owner(req)
    items = req.json().get("items")
    if not isinstance(items, list) or not items:
        raise HTTPError(400, "No dishes to save")
    if len(items) > 300:
        raise HTTPError(400, "Too many dishes at once (max 300)")
    clean = [_menu_item_in(x if isinstance(x, dict) else {}) for x in items]
    with db() as conn:
        for it in clean:
            conn.execute(
                "INSERT INTO menu_items (restaurant_id, name, name_local, category, price_paise, available) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (owner["restaurant_id"], it["name"], it["name_local"], it["category"], it["price_paise"]),
            )
    return {"ok": True, "added": len(clean)}


@route("POST", "/api/owner/menu/csv")
def owner_menu_csv(req: Request):
    owner = require_owner(req)
    _, files = req.form()
    f = files.get("file")
    if f is None:
        raise HTTPError(400, "Choose a CSV file")
    if len(f.data) > 1_000_000:
        raise HTTPError(400, "CSV is too big (max 1 MB)")
    try:
        text = f.data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = f.data.decode("cp1252", errors="replace")  # files saved by Excel on Windows
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPError(400, "The CSV is empty")
    fields = {h.strip().lower(): h for h in reader.fieldnames if h}
    if "name" not in fields or "price" not in fields:
        raise HTTPError(400, "The CSV needs the columns: name, price (and optionally category, name_local)")
    local_key = fields.get("name_local") or fields.get("local_name")
    added = skipped = 0
    with db() as conn:
        for rec in reader:
            name = (rec.get(fields["name"]) or "").strip()
            price_txt = re.sub(r"[^\d.]", "", rec.get(fields["price"]) or "")
            try:
                price = int(round(float(price_txt) * 100))
            except ValueError:
                price = 0
            if not name or price < 100:
                skipped += 1
                continue
            category = ((rec.get(fields["category"]) if "category" in fields else "") or "Menu").strip() or "Menu"
            local = ((rec.get(local_key) if local_key else "") or "").strip()
            conn.execute(
                "INSERT INTO menu_items (restaurant_id, name, name_local, category, price_paise) VALUES (?, ?, ?, ?, ?)",
                (owner["restaurant_id"], name[:80], local[:80], category[:40], price),
            )
            added += 1
    return {"ok": True, "added": added, "skipped": skipped}


@route("POST", "/api/owner/menu/photo")
def owner_menu_photo(req: Request):
    require_owner(req)
    return features.menu_photo(req)  # Sarvam Doc AI (Gemini backup) -> draft menu for the owner to review


@route("GET", "/api/owner/qr")
def owner_qr(req: Request):
    owner = require_owner(req)
    base = public_base(req)
    with db() as conn:
        r = row(conn.execute("SELECT * FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone())
        tables = rows(conn.execute(
            "SELECT id, number, token FROM tables WHERE restaurant_id = ? AND active = 1 ORDER BY number",
            (owner["restaurant_id"],),
        ))
    for t in tables:
        t["url"] = f"{base}/t/{t['token']}"
        t["svg"] = f"/api/owner/qr/{t['id']}.svg"
    local_only = bool(re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])", base))
    return {"restaurant": r, "base_url": base, "local_only": local_only,
            "https": base.startswith("https://"), "tables": tables}


@route("GET", "/api/owner/qr/{table_id:int}.svg")
def owner_qr_svg(req: Request, table_id: int):
    owner = require_owner(req)
    with db() as conn:
        t = row(conn.execute("SELECT token FROM tables WHERE id = ? AND restaurant_id = ?",
                             (table_id, owner["restaurant_id"])).fetchone())
    if t is None:
        raise HTTPError(404, "Table not found")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=1,
                       image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(f"{public_base(req)}/t/{t['token']}")
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    return Response(buf.getvalue(), 200, "image/svg+xml; charset=utf-8", {"Cache-Control": "no-store"})


# ===================================================================== guest

@route("GET", "/api/t/{token}")
def guest_table(req: Request, token: str):
    with db() as conn:
        t = _table_by_token(conn, token)
        active = _active_session(conn, t["id"])
        menu = _menu(conn, t["restaurant_id"], only_available=True)
    return {
        "table": {"number": t["number"]},
        "restaurant": {"name": t["restaurant_name"], "language": t["language"],
                       "wifi_name": t["wifi_name"], "wifi_password": t["wifi_password"]},
        "active_status": active["status"] if active else None,
        "menu": menu,
        "features": config.features(),
    }


@route("POST", "/api/t/{token}/start")
def guest_start(req: Request, token: str):
    device_id = _str(req.json(), "device_id", 0, 64)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        t = _table_by_token(conn, token)
        active = _active_session(conn, t["id"])
        if active:
            if active["status"] == WAITING_APPROVAL:
                raise HTTPError(409, "Someone at this table already asked to start. Once the cashier approves, ask them for the join code.")
            raise HTTPError(409, "This table is already ordering. Ask your friends for the 4-digit join code.")
        code = f"{secrets.randbelow(10000):04d}"
        sid = conn.execute(
            "INSERT INTO table_sessions (table_id, join_code, status, started_at) VALUES (?, ?, ?, ?)",
            (t["id"], code, WAITING_APPROVAL, now_iso()),
        ).lastrowid
        guest_token = _new_guest(conn, sid, device_id)
        features.announce(conn, t["restaurant_id"], t["number"], "start")
    return {"session_id": sid, "guest_token": guest_token}


@route("POST", "/api/t/{token}/join")
def guest_join(req: Request, token: str):
    d = req.json()
    code = _str(d, "code", 1, 8, "the join code")
    device_id = _str(d, "device_id", 0, 64)
    keys = ((f"dev:{device_id or 'none'}", 3), (f"ip:{req.client_ip}", 10))
    now = time.time()
    left = None
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for key, _limit in keys:
            a = conn.execute("SELECT * FROM join_attempts WHERE device_key = ?", (key,)).fetchone()
            if a and a["blocked_until"] > now:
                mins = max(1, int((a["blocked_until"] - now + 59) // 60))
                raise HTTPError(429, f"Too many wrong codes. Try again in {mins} minute{'s' if mins > 1 else ''}.")
        t = _table_by_token(conn, token)
        active = _active_session(conn, t["id"])
        if not active or active["status"] not in (OPEN, BILL_REQUESTED, PAID):
            raise HTTPError(409, "There is no open order at this table yet. Tap Start ordering instead.")
        if secrets.compare_digest(code, active["join_code"]):
            conn.execute("DELETE FROM join_attempts WHERE device_key = ?", (keys[0][0],))
            return {"session_id": active["id"], "guest_token": _new_guest(conn, active["id"], device_id)}
        for key, limit in keys:
            a = conn.execute("SELECT fails FROM join_attempts WHERE device_key = ?", (key,)).fetchone()
            fails = (a["fails"] if a else 0) + 1
            blocked = now + 600 if fails >= limit else 0
            conn.execute(
                "INSERT INTO join_attempts (device_key, fails, blocked_until) VALUES (?, ?, ?) "
                "ON CONFLICT(device_key) DO UPDATE SET fails = excluded.fails, blocked_until = excluded.blocked_until",
                (key, 0 if blocked else fails, blocked),
            )
            if key == keys[0][0]:
                left = 0 if blocked else limit - fails
    # The failed try is saved (the `with` block committed); now report it.
    if left == 0:
        raise HTTPError(429, "Too many wrong codes. This phone is blocked for 10 minutes.")
    raise HTTPError(403, f"Wrong code. {left} tr{'ies' if left != 1 else 'y'} left.")


@route("GET", "/api/session/{session_id:int}")
def guest_session(req: Request, session_id: int):
    with db() as conn:
        return _session_view(conn, _guest_session(conn, session_id, req))


@route("POST", "/api/session/{session_id:int}/orders")
def guest_order(req: Request, session_id: int):
    lines = req.json().get("items")
    if not isinstance(lines, list) or not lines:
        raise HTTPError(400, "Your cart is empty")
    if len(lines) > 40:
        raise HTTPError(400, "Too many different dishes in one order")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _guest_session(conn, session_id, req)
        if s["status"] != OPEN:
            raise HTTPError(409, "Please wait for the cashier to approve your table." if s["status"] == WAITING_APPROVAL
                            else "Ordering is closed for this table.")
        menu = {m["id"]: m for m in _menu(conn, s["restaurant_id"], only_available=True)}
        merged: dict[int, int] = {}
        for line in lines:
            try:
                mid, qty = int(line.get("menu_item_id")), int(line.get("qty"))
            except (TypeError, ValueError, AttributeError):
                raise HTTPError(400, "Bad order line")
            if mid not in menu:
                raise HTTPError(400, "One of the dishes is no longer available. Please refresh the menu.")
            if not 1 <= qty <= 20:
                raise HTTPError(400, "Quantity must be between 1 and 20")
            merged[mid] = min(20, merged.get(mid, 0) + qty)
        ts = now_iso()
        oid = conn.execute(
            "INSERT INTO orders (session_id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, PENDING, ts, ts),
        ).lastrowid
        for mid, qty in merged.items():
            conn.execute(
                "INSERT INTO order_items (order_id, menu_item_id, name, qty, unit_price_paise) VALUES (?, ?, ?, ?, ?)",
                (oid, mid, menu[mid]["name"], qty, menu[mid]["price_paise"]),  # price copied at order time
            )
        features.announce(conn, s["restaurant_id"], s["table_number"], "order",
                          items=[(qty, menu[mid]) for mid, qty in merged.items()])
        return {"ok": True, "order_id": oid, "session": _session_view(conn, s)}


@route("POST", "/api/session/{session_id:int}/call-waiter")
def guest_call_waiter(req: Request, session_id: int):
    reason = _str(req.json(), "reason", 0, 120)
    with db() as conn:
        s = _guest_session(conn, session_id, req)
        _call_waiter(conn, s, reason)
    return {"ok": True}


def _call_waiter(conn, s: dict, reason: str = "") -> bool:
    """Shared by the button and voice. Returns True if a new call was made (False if one is already open)."""
    if s["status"] not in (OPEN, BILL_REQUESTED, PAID):
        raise HTTPError(409, "The table is not open.")
    if conn.execute("SELECT 1 FROM waiter_calls WHERE session_id = ? AND done = 0", (s["id"],)).fetchone():
        return False
    conn.execute("INSERT INTO waiter_calls (session_id, reason, created_at) VALUES (?, ?, ?)", (s["id"], reason, now_iso()))
    features.announce(conn, s["restaurant_id"], s["table_number"], "waiter")
    return True


def _request_bill(conn, s: dict) -> None:
    """Shared by the button and voice. Blocks new orders; the bill is summed from accepted items."""
    if s["status"] == BILL_REQUESTED:
        return
    if s["status"] != OPEN:
        raise HTTPError(409, "The bill can't be requested right now.")
    if conn.execute("SELECT 1 FROM orders WHERE session_id = ? AND status = ?", (s["id"], PENDING)).fetchone():
        raise HTTPError(409, "Your last order is still waiting for the cashier. Try again in a moment.")
    if _bill_paise(conn, s["id"]) <= 0:
        raise HTTPError(409, "Nothing has been ordered yet.")
    conn.execute("UPDATE table_sessions SET status = ? WHERE id = ?", (BILL_REQUESTED, s["id"]))
    s["status"] = BILL_REQUESTED
    features.announce(conn, s["restaurant_id"], s["table_number"], "bill")


@route("POST", "/api/session/{session_id:int}/request-bill")
def guest_request_bill(req: Request, session_id: int):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _guest_session(conn, session_id, req)
        _request_bill(conn, s)
        return {"ok": True, "session": _session_view(conn, s)}


def _valid_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise HTTPError(400, "Please enter a valid 10-digit mobile number")
    return digits


@route("POST", "/api/session/{session_id:int}/pay")
def guest_pay(req: Request, session_id: int):
    phone = _valid_phone(str(req.json().get("phone") or ""))
    if not config.cashfree_ready():
        raise HTTPError(503, "Online payment isn't set up here. Please pay at the counter.")
    with db() as conn:
        s = _guest_session(conn, session_id, req)
        if s["status"] in (PAID, PAID_CASH, CLOSED):
            raise HTTPError(409, "This bill is already paid.")
        if s["status"] != BILL_REQUESTED:
            raise HTTPError(409, "Please request the bill first.")
        amount = _bill_paise(conn, session_id)  # always from the database, never from the phone
        if amount <= 0:
            raise HTTPError(409, "Nothing to pay.")
        restaurant = conn.execute("SELECT name FROM restaurants WHERE id = ?", (s["restaurant_id"],)).fetchone()["name"]
        pay = _latest_payment(conn, session_id)
        conn.execute("UPDATE table_sessions SET guest_phone = ? WHERE id = ?", (phone, session_id))
        count = conn.execute("SELECT COUNT(*) FROM payments WHERE session_id = ?", (session_id,)).fetchone()[0]
    if pay and pay["status"] == "ACTIVE":
        if _check_payment(pay["link_id"]) == "PAID":
            raise HTTPError(409, "This bill is already paid.")
        with db() as conn:
            pay = row(conn.execute("SELECT * FROM payments WHERE id = ?", (pay["id"],)).fetchone())
        if pay["status"] == "ACTIVE" and pay["amount_paise"] == amount and pay["expires_at"] > now_iso():
            return {"link_url": pay["link_url"], "amount_paise": amount}
    # One link per bill: session id + counter (+ a little randomness so a reset database never repeats an id).
    link_id = f"bd{session_id}c{count + 1}{secrets.token_hex(2)}"
    base = public_base(req)
    try:
        link = cashfree.create_link(
            link_id, amount, phone, f"{restaurant} - Table {s['table_number']}",
            return_url=f"{base}/paid?session={session_id}",
            notify_url=f"{base}/api/webhooks/cashfree",
        )
    except cashfree.CashfreeError as e:
        raise HTTPError(502, str(e))
    expires = (datetime.now(timezone.utc) + timedelta(minutes=29)).isoformat(timespec="seconds")
    with db() as conn:
        conn.execute("UPDATE payments SET status = 'REPLACED' WHERE session_id = ? AND status = 'ACTIVE'", (session_id,))
        conn.execute(
            "INSERT INTO payments (session_id, link_id, link_url, amount_paise, status, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)",
            (session_id, link_id, link["link_url"], amount, now_iso(), expires),
        )
    return {"link_url": link["link_url"], "amount_paise": amount}


def _check_payment(link_id: str) -> str:
    """Ask Cashfree about a link and record the result. Safe to call many times (duplicates do nothing)."""
    with db() as conn:
        pay = row(conn.execute("SELECT * FROM payments WHERE link_id = ?", (link_id,)).fetchone())
    if pay is None:
        return "UNKNOWN"
    if pay["status"] == "PAID":
        return "PAID"
    try:
        link = cashfree.get_link(link_id)
    except cashfree.CashfreeError:
        return pay["status"]
    if cashfree.is_paid(link, pay["amount_paise"]):
        ts = now_iso()
        with db() as conn:
            cur = conn.execute("UPDATE payments SET status = 'PAID', paid_at = ? WHERE id = ? AND status != 'PAID'",
                               (ts, pay["id"]))
            if cur.rowcount:
                conn.execute(
                    "UPDATE table_sessions SET status = ?, settled_paise = ?, settled_at = ?, pay_method = 'ONLINE' "
                    "WHERE id = ? AND status IN (?, ?)",
                    (PAID, pay["amount_paise"], ts, pay["session_id"], OPEN, BILL_REQUESTED),
                )
                where = conn.execute("SELECT t.restaurant_id, t.number FROM table_sessions s JOIN tables t "
                                     "ON t.id = s.table_id WHERE s.id = ?", (pay["session_id"],)).fetchone()
                if where:  # only after Cashfree confirmed it
                    features.announce(conn, where["restaurant_id"], where["number"], "paid", amount_paise=pay["amount_paise"])
        return "PAID"
    status = str(link.get("link_status", "")).upper()
    if status in ("EXPIRED", "CANCELLED") and pay["status"] == "ACTIVE":
        with db() as conn:
            conn.execute("UPDATE payments SET status = ? WHERE id = ? AND status = 'ACTIVE'", (status, pay["id"]))
        return status
    return pay["status"]


GAMES = {"dosa": 20000, "chai": 50000, "memory": 1000, "runner": 500000}  # game id -> highest believable score


@route("POST", "/api/session/{session_id:int}/score")
def guest_score(req: Request, session_id: int):
    d = req.json()
    game = str(d.get("game") or "")
    if game not in GAMES:
        raise HTTPError(400, "Unknown game")
    score = _int(d, "score", 0, GAMES[game], "score")
    # Keep any script (Kannada vowel signs are combining marks); drop markup and control characters.
    player = re.sub(r"[<>\"`&\\/{}\[\]\x00-\x1f\x7f]", "", _str(d, "player", 0, 40)).strip()[:16] or "Guest"
    with db() as conn:
        s = _guest_session(conn, session_id, req)
        if s["status"] in (CLOSED, REJECTED, PAID_CASH):
            raise HTTPError(409, "This table is closed.")
        if conn.execute("SELECT COUNT(*) FROM game_scores WHERE restaurant_id = ? AND table_number = ? AND created_at >= ?",
                        (s["restaurant_id"], s["table_number"], s["started_at"])).fetchone()[0] >= 300:
            raise HTTPError(429, "That's a lot of games! Scores are paused for this table.")
        conn.execute(
            "INSERT INTO game_scores (restaurant_id, game, player, table_number, score, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (s["restaurant_id"], game, player, s["table_number"], score, now_iso()),
        )
    return {"ok": True}


@route("GET", "/api/t/{token}/leaderboard")
def guest_leaderboard(req: Request, token: str):
    game = req.query.get("game", "")
    if game not in GAMES:
        raise HTTPError(400, "Unknown game")
    with db() as conn:
        t = _table_by_token(conn, token)
        top = rows(conn.execute(
            "SELECT player, table_number, MAX(score) AS score FROM game_scores "
            "WHERE restaurant_id = ? AND game = ? AND created_at >= ? GROUP BY player, table_number "
            "ORDER BY score DESC LIMIT 5",
            (t["restaurant_id"], game, _ist_today_start_utc()),
        ))
    return {"top": top}


@route("GET", "/api/session/{session_id:int}/payment-status")
def guest_payment_status(req: Request, session_id: int):
    with db() as conn:
        _guest_session(conn, session_id, req)
        pay = _latest_payment(conn, session_id)
    if pay and pay["status"] == "ACTIVE":
        _check_payment(pay["link_id"])
    with db() as conn:
        return _session_view(conn, _guest_session(conn, session_id, req))


@route("POST", "/api/webhooks/cashfree")
def cashfree_webhook(req: Request):
    if not cashfree.verify_signature(req.body, req.header("x-webhook-timestamp"), req.header("x-webhook-signature")):
        raise HTTPError(401, "Bad signature")
    try:
        payload = json.loads(req.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"ok": True}
    link_id = cashfree.find_link_id(payload) if isinstance(payload, dict) else None
    if link_id:
        _check_payment(link_id)  # never trust the webhook alone: confirm with Cashfree
    return {"ok": True}


@route("POST", "/api/session/{session_id:int}/assistant")
def guest_assistant(req: Request, session_id: int):
    f = config.features()
    if not f["voice_order"]:
        raise HTTPError(404, "Not found")
    fields, files = req.form()
    with db() as conn:
        s = _guest_session(conn, session_id, req)
        menu = _menu(conn, s["restaurant_id"], only_available=True)
    if s["status"] not in (OPEN, BILL_REQUESTED):
        raise HTTPError(409, "The table is not open for ordering.")
    audio = files.get("audio")
    wav = audio.data if audio is not None and audio.data else None
    if wav is not None and len(wav) > 6_000_000:
        raise HTTPError(400, "That recording is too long. Keep it under 20 seconds.")
    text = (fields.get("text") or "").strip()[:300] or None
    if not wav and not text:
        raise HTTPError(400, "Say or type what you'd like.")
    if not menu:
        raise HTTPError(409, "The menu is empty.")
    try:
        result = gemini.understand_order(menu, audio_wav=wav, text=text,
                                         allow_budget=f["budget_order"], allow_actions=f["voice_actions"])
    except gemini.GeminiError as e:
        raise HTTPError(502, str(e))

    by_id = {m["id"]: m for m in menu}
    intent = str(result.get("intent") or "unknown")
    if intent == "budget" and not f["budget_order"]:
        intent = "order"
    if intent in ("bill", "waiter") and not f["voice_actions"]:
        intent = "unknown"
    if intent not in ("order", "budget", "bill", "waiter"):
        intent = "unknown"
    lines: dict[int, int] = {}
    for it in result.get("items") or []:
        try:
            mid, qty = int(it.get("id")), int(it.get("qty") or 1)
        except (TypeError, ValueError, AttributeError):
            continue
        if mid in by_id and qty > 0:
            lines[mid] = min(20, lines.get(mid, 0) + qty)

    budget_paise = None
    if intent == "budget":
        try:
            budget_paise = int(round(float(result.get("budget_rupees") or 0) * 100)) or None
        except (TypeError, ValueError):
            budget_paise = None
        if budget_paise:
            # Enforce the budget ourselves: remove the priciest dishes until it fits.
            while lines and sum(by_id[m]["price_paise"] * q for m, q in lines.items()) > budget_paise:
                priciest = max(lines, key=lambda m: by_id[m]["price_paise"])
                lines[priciest] -= 1
                if lines[priciest] <= 0:
                    del lines[priciest]

    items = [{"id": mid, "name": by_id[mid]["name"], "name_local": by_id[mid]["name_local"],
              "category": by_id[mid]["category"], "qty": qty, "price_paise": by_id[mid]["price_paise"]}
             for mid, qty in lines.items()]
    if intent in ("order", "budget") and not items:
        intent = "unknown"
    people = result.get("people")
    return {
        "transcript": str(result.get("transcript") or text or "")[:400],
        "intent": intent,
        "reply": str(result.get("reply") or "")[:300],
        "items": items,
        "total_paise": sum(i["price_paise"] * i["qty"] for i in items),
        "budget_paise": budget_paise,
        "people": people if isinstance(people, int) else None,
    }


# ===================================================================== cashier

ORDER_FLOW = {PENDING: {ACCEPTED, ORDER_REJECTED}, ACCEPTED: {PREPARING, SERVED}, PREPARING: {SERVED}}


def _ist_today_start_utc() -> str:
    start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat(timespec="seconds")


@route("GET", "/api/dashboard")
def dashboard(req: Request):
    owner = require_owner(req)
    rid = owner["restaurant_id"]
    with db() as conn:
        r = row(conn.execute("SELECT * FROM restaurants WHERE id = ?", (rid,)).fetchone())
        tables = rows(conn.execute(
            "SELECT id, number FROM tables WHERE restaurant_id = ? AND active = 1 ORDER BY number", (rid,)
        ))
        for t in tables:
            s = _active_session(conn, t["id"])
            if not s:
                t["session"] = None
                continue
            orders = _orders_with_items(conn, s["id"])
            pay = _latest_payment(conn, s["id"])
            t["session"] = {
                "id": s["id"],
                "status": s["status"],
                "join_code": s["join_code"],
                "started_at": s["started_at"],
                "guest_phone": s["guest_phone"],
                "guests": conn.execute("SELECT COUNT(*) FROM session_guests WHERE session_id = ?", (s["id"],)).fetchone()[0],
                "orders": orders,
                "pending_count": sum(1 for o in orders if o["status"] == PENDING),
                "item_count": sum(i["qty"] for o in orders if o["status"] in BILLABLE_ORDER_STATUSES for i in o["items"]),
                "bill_paise": _bill_paise(conn, s["id"]),
                "waiter_calls": rows(conn.execute(
                    "SELECT id, reason, created_at FROM waiter_calls WHERE session_id = ? AND done = 0", (s["id"],)
                )),
                "payment": {"status": pay["status"], "amount_paise": pay["amount_paise"]} if pay else None,
            }
        revenue = conn.execute(
            "SELECT COALESCE(SUM(s.settled_paise), 0), COUNT(*) FROM table_sessions s JOIN tables t ON t.id = s.table_id "
            "WHERE t.restaurant_id = ? AND s.settled_at >= ? AND s.status IN (?, ?, ?)",
            (rid, _ist_today_start_utc(), PAID, PAID_CASH, CLOSED),
        ).fetchone()
        extras = features.dashboard_extras(conn, rid)
    return {
        "restaurant": r,
        "tables": tables,
        "stats": {"revenue_today_paise": int(revenue[0]), "bills_today": int(revenue[1])},
        "features": config.features(),
        "server_time": now_iso(),
        **extras,  # announcements (Kannada alerts) and quiz prizes
    }


@route("POST", "/api/session/{session_id:int}/approve")
def cashier_approve(req: Request, session_id: int):
    owner = require_owner(req)
    with db() as conn:
        s = _owner_session(conn, session_id, owner)
        if s["status"] != WAITING_APPROVAL:
            raise HTTPError(409, "This table is not waiting for approval.")
        conn.execute("UPDATE table_sessions SET status = ? WHERE id = ?", (OPEN, session_id))
    return {"ok": True}


@route("POST", "/api/session/{session_id:int}/reject")
def cashier_reject(req: Request, session_id: int):
    owner = require_owner(req)
    with db() as conn:
        s = _owner_session(conn, session_id, owner)
        if s["status"] != WAITING_APPROVAL:
            raise HTTPError(409, "Only a waiting table can be rejected. Use Free table instead.")
        conn.execute("UPDATE table_sessions SET status = ?, closed_at = ? WHERE id = ?", (REJECTED, now_iso(), session_id))
    return {"ok": True}


@route("POST", "/api/orders/{order_id:int}/status")
def cashier_order_status(req: Request, order_id: int):
    owner = require_owner(req)
    d = req.json()
    new = str(d.get("status") or "").upper()
    reason = _str(d, "reason", 0, 160)
    with db() as conn:
        o = row(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
        if o is None:
            raise HTTPError(404, "Order not found")
        s = _owner_session(conn, o["session_id"], owner)
        if s["status"] not in (OPEN, BILL_REQUESTED, PAID):
            raise HTTPError(409, "This table is closed.")
        if new not in ORDER_FLOW.get(o["status"], set()):
            raise HTTPError(409, f"Can't change an order from {o['status'].lower()} to {new.lower()}.")
        conn.execute("UPDATE orders SET status = ?, reject_reason = ?, updated_at = ? WHERE id = ?",
                     (new, reason if new == ORDER_REJECTED else o["reject_reason"], now_iso(), order_id))
    return {"ok": True}


@route("POST", "/api/session/{session_id:int}/cash")
def cashier_cash(req: Request, session_id: int):
    owner = require_owner(req)
    with db() as conn:
        s = _owner_session(conn, session_id, owner)
        if s["status"] not in (OPEN, BILL_REQUESTED):
            raise HTTPError(409, "This table can't be marked as paid in cash now.")
        links = [p["link_id"] for p in rows(conn.execute(
            "SELECT link_id FROM payments WHERE session_id = ? AND status = 'ACTIVE'", (session_id,)
        ))]
    for link_id in links:  # if the guest just paid online, don't take cash too
        if _check_payment(link_id) == "PAID":
            raise HTTPError(409, "This bill was just paid online. No cash needed.")
    ts = now_iso()
    with db() as conn:
        amount = _bill_paise(conn, session_id)
        conn.execute("UPDATE orders SET status = ?, reject_reason = 'Table closed', updated_at = ? "
                     "WHERE session_id = ? AND status = ?", (ORDER_REJECTED, ts, session_id, PENDING))
        conn.execute("UPDATE table_sessions SET status = ?, settled_paise = ?, settled_at = ?, pay_method = 'CASH', "
                     "closed_at = ? WHERE id = ?", (PAID_CASH, amount, ts, ts, session_id))
        conn.execute("UPDATE payments SET status = 'CANCELLED' WHERE session_id = ? AND status = 'ACTIVE'", (session_id,))
        conn.execute("UPDATE waiter_calls SET done = 1 WHERE session_id = ?", (session_id,))
    for link_id in links:
        cashfree.cancel_link(link_id)
    return {"ok": True}


@route("POST", "/api/session/{session_id:int}/free")
def cashier_free(req: Request, session_id: int):
    owner = require_owner(req)
    force = req.query.get("force") in ("1", "true")
    with db() as conn:
        s = _owner_session(conn, session_id, owner)
        if s["status"] not in ACTIVE_SESSION_STATUSES:
            return {"ok": True}
        if s["status"] != PAID and _bill_paise(conn, session_id) > 0 and not force:
            raise HTTPError(409, "This table has an unpaid bill.")
        ts = now_iso()
        conn.execute("UPDATE orders SET status = ?, reject_reason = 'Table closed', updated_at = ? "
                     "WHERE session_id = ? AND status = ?", (ORDER_REJECTED, ts, session_id, PENDING))
        conn.execute("UPDATE table_sessions SET status = ?, closed_at = ? WHERE id = ?", (CLOSED, ts, session_id))
        conn.execute("UPDATE payments SET status = 'CANCELLED' WHERE session_id = ? AND status = 'ACTIVE'", (session_id,))
        conn.execute("UPDATE waiter_calls SET done = 1 WHERE session_id = ?", (session_id,))
    return {"ok": True}


@route("POST", "/api/waiter-calls/{call_id:int}/done")
def cashier_waiter_done(req: Request, call_id: int):
    owner = require_owner(req)
    with db() as conn:
        c = row(conn.execute("SELECT * FROM waiter_calls WHERE id = ?", (call_id,)).fetchone())
        if c is None:
            raise HTTPError(404, "Not found")
        _owner_session(conn, c["session_id"], owner)
        conn.execute("UPDATE waiter_calls SET done = 1 WHERE id = ?", (call_id,))
    return {"ok": True}


@route("GET", "/api/announce")
def announce(req: Request):
    require_owner(req)
    if not config.features()["gemini_tts"]:
        raise HTTPError(503, "Gemini voice is off")
    text = (req.query.get("text") or "").strip()[:200]
    if not text:
        raise HTTPError(400, "No text")
    try:
        wav = gemini.speak(text)
    except gemini.GeminiError as e:
        raise HTTPError(502, str(e))
    return Response(wav, 200, "audio/wav", {"Cache-Control": "private, max-age=86400"})


@route("GET", "/api/health")
def health(req: Request):
    return {"ok": True, "features": config.features()}


# Sarvam features, budget order and the table quiz live in features.py. Imported last so it can use the
# helpers above; its routes register on the same app.
from . import features  # noqa: E402
