"""Restaurant upgrades: kitchen TV (3), staff + waiter portal (2), private game rooms (5), daily report.

Each part has its own switch in config.py. Permission checks are all here on the server.
"""
import base64
import secrets

from . import ai, config, features
from . import main as m
from .db import ACCEPTED, ACTIVE_SESSION_STATUSES, PREPARING, db, now_iso, row, rows
from .web import HTTPError, Request, file_response

route = m.app.route


def _off():
    raise HTTPError(404, "Not found")


# ===================================================================== 3. kitchen TV

def _kitchen_restaurant(conn, token: str) -> dict:
    if not config.FEATURE_KITCHEN_TV:
        _off()
    if not token or len(token) < 24:
        raise HTTPError(404, "This kitchen link is not valid any more.")
    r = row(conn.execute("SELECT id, name, language, kitchen_token FROM restaurants WHERE kitchen_token = ?", (token,)).fetchone())
    if r is None or not secrets.compare_digest(r["kitchen_token"], token):
        raise HTTPError(404, "This kitchen link is not valid any more. Ask the owner for the new one.")
    return r


def _kitchen_url(req: Request, token: str) -> str:
    return f"{m.public_base(req)}/kitchen/{token}"


@route("GET", "/api/owner/kitchen-link")
def kitchen_link(req: Request):
    owner = m.require_owner(req)
    if not config.FEATURE_KITCHEN_TV:
        _off()
    with db() as conn:
        tok = conn.execute("SELECT kitchen_token FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()[0]
        if not tok:
            tok = secrets.token_urlsafe(24)
            conn.execute("UPDATE restaurants SET kitchen_token = ? WHERE id = ?", (tok, owner["restaurant_id"]))
    return {"url": _kitchen_url(req, tok)}


@route("POST", "/api/owner/kitchen-link/regenerate")
def kitchen_link_regenerate(req: Request):
    owner = m.require_owner(req)
    if not config.FEATURE_KITCHEN_TV:
        _off()
    tok = secrets.token_urlsafe(24)
    with db() as conn:
        conn.execute("UPDATE restaurants SET kitchen_token = ? WHERE id = ?", (tok, owner["restaurant_id"]))
    return {"url": _kitchen_url(req, tok)}


@route("GET", "/kitchen/{token}")
def kitchen_page(req: Request, token: str):
    if not config.FEATURE_KITCHEN_TV:
        _off()
    return file_response(config.STATIC_DIR / "pages" / "kitchen.html")


def kitchen_tickets(conn, restaurant_id: int) -> list[dict]:
    """Accepted / preparing orders of open tables. Names and quantities only: no prices, phones or totals."""
    marks = ",".join("?" * len(ACTIVE_SESSION_STATUSES))
    orders = rows(conn.execute(
        f"SELECT o.id, o.session_id, o.status, o.accepted_at, o.updated_at, t.number AS table_number, t.seats "
        f"FROM orders o JOIN table_sessions s ON s.id = o.session_id JOIN tables t ON t.id = s.table_id "
        f"WHERE t.restaurant_id = ? AND o.status IN (?, ?) AND s.status IN ({marks}) ORDER BY COALESCE(o.accepted_at, o.updated_at), o.id",
        (restaurant_id, ACCEPTED, PREPARING, *ACTIVE_SESSION_STATUSES)))
    out = []
    for o in orders:
        n = conn.execute("SELECT COUNT(*) FROM orders WHERE session_id = ? AND id <= ?", (o["session_id"], o["id"])).fetchone()[0]
        items = rows(conn.execute(
            "SELECT oi.name, oi.qty, COALESCE(mi.name_local, '') AS name_local FROM order_items oi "
            "LEFT JOIN menu_items mi ON mi.id = oi.menu_item_id WHERE oi.order_id = ? ORDER BY oi.id", (o["id"],)))
        out.append({"order_id": o["id"], "table_number": o["table_number"], "seats": o["seats"] if config.FEATURE_SEATS else None,
                    "order_no": n, "items": items, "accepted_at": o["accepted_at"] or o["updated_at"], "status": o["status"]})
    return out


@route("GET", "/api/kitchen/{token}/board")
def kitchen_board(req: Request, token: str):
    with db() as conn:
        r = _kitchen_restaurant(conn, token)
        tickets = kitchen_tickets(conn, r["id"])
        ann = rows(conn.execute(
            "SELECT id, table_number, text_kn, text_en FROM announcements WHERE restaurant_id = ? AND event_type = 'kitchen_order' "
            "AND kitchen_claimed = 0 AND created_at >= ? ORDER BY id", (r["id"], features._ago_iso(120))))
    return {"restaurant": {"name": r["name"], "language": r["language"]}, "tickets": tickets,
            "announcements": ann if config.FEATURE_KANNADA_ALERTS else [], "server_time": now_iso()}


@route("POST", "/api/kitchen/{token}/announcements/{ann_id:int}/claim")
def kitchen_claim(req: Request, token: str, ann_id: int):
    """The kitchen TV claims its own copy of an announcement (separate from the cashier dashboard's claim)."""
    with db() as conn:
        r = _kitchen_restaurant(conn, token)
        a = row(conn.execute("SELECT * FROM announcements WHERE id = ? AND restaurant_id = ? AND event_type = 'kitchen_order'",
                             (ann_id, r["id"])).fetchone())
        if a is None:
            raise HTTPError(404, "Not found")
        won = conn.execute("UPDATE announcements SET kitchen_claimed = 1 WHERE id = ? AND kitchen_claimed = 0", (ann_id,)).rowcount == 1
    out = {"id": ann_id, "audio": None, "text_kn": a["text_kn"], "text_en": a["text_en"], "spoken_here": won}
    if won:
        text, lang = (a["text_en"], "en-IN") if r["language"] == "en-IN" else (a["text_kn"], "kn-IN")
        try:
            out["audio"] = "data:audio/wav;base64," + base64.b64encode(ai.tts(text, lang)).decode()
        except ai.AIError:
            pass  # the TV falls back to the browser voice
    return out


def on_order_status(conn, order: dict, new_status: str, restaurant_id: int, table_number: int) -> None:
    """Hook from the order-status route: remember when it was accepted and tell the kitchen (once)."""
    if new_status != ACCEPTED:
        return
    conn.execute("UPDATE orders SET accepted_at = ? WHERE id = ? AND accepted_at IS NULL", (now_iso(), order["id"]))
    if config.FEATURE_KITCHEN_TV:
        items = rows(conn.execute(
            "SELECT oi.qty, oi.name, COALESCE(mi.name_local, '') AS name_local FROM order_items oi "
            "LEFT JOIN menu_items mi ON mi.id = oi.menu_item_id WHERE oi.order_id = ? ORDER BY oi.id", (order["id"],)))
        features.announce(conn, restaurant_id, table_number, "kitchen_order", items=[(i["qty"], i) for i in items])


# ===================================================================== 2. staff accounts + waiter portal

import re  # noqa: E402
import time  # noqa: E402

from .auth import STAFF_COOKIE, STAFF_MAX_AGE, hash_password, make_staff_cookie, read_owner_cookie, read_staff_cookie, verify_password  # noqa: E402
from .auth import COOKIE_NAME as OWNER_COOKIE  # noqa: E402

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,20}$")
PIN_RE = re.compile(r"^\d{4,6}$")


def _staff_on():
    if not config.FEATURE_STAFF:
        _off()


def require_staff(req: Request, roles=("waiter",)) -> dict:
    """The logged-in staff member: {staff_id, restaurant_id, role, name, label, table_ids (None = all tables)}."""
    _staff_on()
    sid = next((x for x in map(read_staff_cookie, req.cookie_all(STAFF_COOKIE)) if x is not None), None)
    if sid is None:
        raise HTTPError(401, "Please log in")
    with db() as conn:
        st = row(conn.execute("SELECT * FROM staff WHERE id = ? AND active = 1", (sid,)).fetchone())
        if st is None:
            raise HTTPError(401, "Please log in")
        tids = [r[0] for r in conn.execute("SELECT table_id FROM staff_tables WHERE staff_id = ?", (sid,))]
    if st["role"] not in roles:
        raise HTTPError(403, "Your account can't do this.")
    return {"staff_id": st["id"], "restaurant_id": st["restaurant_id"], "role": st["role"], "name": st["name"],
            "label": f"{st['role']}:{st['name']}", "table_ids": tids or None, "is_owner": False}


def actor(req: Request) -> dict:
    """Owner (full access) or, with FEATURE_STAFF on, a waiter. Used only by the table actions waiters may do."""
    owner_ok = any(read_owner_cookie(v) is not None for v in req.cookie_all(OWNER_COOKIE))
    if owner_ok or not config.FEATURE_STAFF or not req.cookie_all(STAFF_COOKIE):
        o = m.require_owner(req)
        return dict(o, label="owner", table_ids=None, is_owner=True)
    return require_staff(req, roles=("waiter",))


def session_for(conn, session_id: int, who: dict) -> dict:
    """The table session if `who` may act on it. Owner: same 404 as before. Waiter: 403 for other restaurants/tables."""
    if who["is_owner"]:
        return m._owner_session(conn, session_id, who)
    s = row(conn.execute("SELECT s.*, t.number AS table_number, t.restaurant_id FROM table_sessions s "
                         "JOIN tables t ON t.id = s.table_id WHERE s.id = ?", (session_id,)).fetchone())
    if s is None:
        raise HTTPError(404, "Table session not found")
    if s["restaurant_id"] != who["restaurant_id"] or (who["table_ids"] is not None and s["table_id"] not in who["table_ids"]):
        raise HTTPError(403, "This table isn't assigned to you.")
    return s


# ---------------- owner: manage staff

def _staff_list(conn, rid: int, base: str) -> list[dict]:
    slug = conn.execute("SELECT slug FROM restaurants WHERE id = ?", (rid,)).fetchone()[0]
    out = []
    for s in rows(conn.execute("SELECT id, name, role, username, active, created_at FROM staff WHERE restaurant_id = ? ORDER BY active DESC, name", (rid,))):
        s["table_ids"] = [r[0] for r in conn.execute("SELECT table_id FROM staff_tables WHERE staff_id = ?", (s["id"],))]
        s["login_url"] = f"{base}/staff/login?r={slug}&u={s['username']}"
        out.append(s)
    return out


def _table_ids_in(conn, rid: int, ids) -> list[int]:
    if ids in (None, "all"):
        return []
    if not isinstance(ids, list):
        raise HTTPError(400, "Tables must be a list")
    valid = {r[0] for r in conn.execute("SELECT id FROM tables WHERE restaurant_id = ? AND active = 1", (rid,))}
    try:
        ids = sorted({int(x) for x in ids})
    except (TypeError, ValueError):
        raise HTTPError(400, "Bad table list")
    if any(i not in valid for i in ids):
        raise HTTPError(400, "Unknown table")
    return ids


@route("GET", "/api/owner/staff")
def staff_list(req: Request):
    owner = m.require_owner(req)
    _staff_on()
    with db() as conn:
        tables = rows(conn.execute("SELECT id, number, seats FROM tables WHERE restaurant_id = ? AND active = 1 ORDER BY number", (owner["restaurant_id"],)))
        slug = conn.execute("SELECT slug FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()[0]
        return {"staff": _staff_list(conn, owner["restaurant_id"], m.public_base(req)), "tables": tables, "restaurant_code": slug,
                "login_url": f"{m.public_base(req)}/staff/login?r={slug}"}


@route("POST", "/api/owner/staff")
def staff_add(req: Request):
    owner = m.require_owner(req)
    _staff_on()
    d = req.json()
    name = m._str(d, "name", 1, 40, "the waiter's name")
    username = str(d.get("username") or "").strip().lower()
    pin = str(d.get("pin") or "").strip()
    role = d.get("role") if d.get("role") in ("waiter", "kitchen") else "waiter"
    if not USERNAME_RE.match(username):
        raise HTTPError(400, "Username: 3 to 20 letters, numbers, dot, dash or underscore")
    if not PIN_RE.match(pin):
        raise HTTPError(400, "PIN must be 4 to 6 digits")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM staff WHERE restaurant_id = ? AND username = ?", (owner["restaurant_id"], username)).fetchone():
            raise HTTPError(409, "That username is taken")
        tids = _table_ids_in(conn, owner["restaurant_id"], d.get("table_ids"))
        sid = conn.execute("INSERT INTO staff (restaurant_id, name, role, username, pin_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (owner["restaurant_id"], name, role, username, hash_password(pin), now_iso())).lastrowid
        for t in tids:
            conn.execute("INSERT INTO staff_tables (staff_id, table_id) VALUES (?, ?)", (sid, t))
    return {"ok": True, "id": sid}


@route("PUT", "/api/owner/staff/{staff_id:int}")
def staff_edit(req: Request, staff_id: int):
    owner = m.require_owner(req)
    _staff_on()
    d = req.json()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        st = row(conn.execute("SELECT * FROM staff WHERE id = ? AND restaurant_id = ?", (staff_id, owner["restaurant_id"])).fetchone())
        if st is None:
            raise HTTPError(404, "Staff member not found")
        if "name" in d:
            conn.execute("UPDATE staff SET name = ? WHERE id = ?", (m._str(d, "name", 1, 40, "the name"), staff_id))
        if "pin" in d:
            pin = str(d.get("pin") or "").strip()
            if not PIN_RE.match(pin):
                raise HTTPError(400, "PIN must be 4 to 6 digits")
            conn.execute("UPDATE staff SET pin_hash = ? WHERE id = ?", (hash_password(pin), staff_id))
        if "active" in d:
            conn.execute("UPDATE staff SET active = ? WHERE id = ?", (1 if d.get("active") else 0, staff_id))
        if "table_ids" in d:
            tids = _table_ids_in(conn, owner["restaurant_id"], d.get("table_ids"))
            conn.execute("DELETE FROM staff_tables WHERE staff_id = ?", (staff_id,))
            for t in tids:
                conn.execute("INSERT INTO staff_tables (staff_id, table_id) VALUES (?, ?)", (staff_id, t))
    return {"ok": True}


# ---------------- staff login

@route("POST", "/api/staff/login")
def staff_login(req: Request):
    _staff_on()
    d = req.json()
    slug = str(d.get("restaurant") or "").strip().lower()[:80]
    username = str(d.get("username") or "").strip().lower()[:20]
    pin = str(d.get("pin") or "").strip()[:6]
    keys = ((f"staff:{slug}:{username}", 5), (f"staffip:{req.client_ip}", 20))
    now = time.time()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for key, _ in keys:
            a = conn.execute("SELECT * FROM join_attempts WHERE device_key = ?", (key,)).fetchone()
            if a and a["blocked_until"] > now:
                raise HTTPError(429, f"Too many wrong PINs. Try again in {max(1, int((a['blocked_until'] - now + 59) // 60))} min.")
        st = row(conn.execute("SELECT s.* FROM staff s JOIN restaurants r ON r.id = s.restaurant_id "
                              "WHERE r.slug = ? AND s.username = ? AND s.active = 1", (slug, username)).fetchone())
        if st and verify_password(pin, st["pin_hash"]):
            conn.execute("DELETE FROM join_attempts WHERE device_key = ?", (keys[0][0],))
            ok = st
        else:
            ok = None
            for key, limit in keys:
                a = conn.execute("SELECT fails FROM join_attempts WHERE device_key = ?", (key,)).fetchone()
                fails = (a["fails"] if a else 0) + 1
                blocked = now + 600 if fails >= limit else 0
                conn.execute("INSERT INTO join_attempts (device_key, fails, blocked_until) VALUES (?, ?, ?) ON CONFLICT(device_key) "
                             "DO UPDATE SET fails = excluded.fails, blocked_until = excluded.blocked_until", (key, 0 if blocked else fails, blocked))
    if not ok:
        raise HTTPError(403, "Wrong restaurant code, username or PIN")
    resp = m.json_response({"ok": True, "name": ok["name"], "role": ok["role"], "next": "/waiter"})
    resp.set_cookie(STAFF_COOKIE, make_staff_cookie(ok["id"]), max_age=STAFF_MAX_AGE)
    return resp


@route("POST", "/api/staff/logout")
def staff_logout(req: Request):
    resp = m.json_response({"ok": True})
    resp.delete_cookie(STAFF_COOKIE)
    return resp


@route("GET", "/staff/login")
def staff_login_page(req: Request):
    _staff_on()
    return file_response(config.STATIC_DIR / "pages" / "staff_login.html")


@route("GET", "/waiter")
def waiter_page(req: Request):
    _staff_on()
    return file_response(config.STATIC_DIR / "pages" / "waiter.html")


@route("GET", "/owner/staff")
def staff_page(req: Request):
    _staff_on()
    return file_response(config.STATIC_DIR / "pages" / "staff.html")


@route("GET", "/api/waiter/board")
def waiter_board(req: Request):
    """Only the waiter's tables. No revenue, totals, prices, payments, menu editing or settings."""
    st = require_staff(req, roles=("waiter",))
    with db() as conn:
        r = row(conn.execute("SELECT name, language FROM restaurants WHERE id = ?", (st["restaurant_id"],)).fetchone())
        q = "SELECT id, number, seats, merged_into FROM tables WHERE restaurant_id = ? AND active = 1"
        args = [st["restaurant_id"]]
        if st["table_ids"] is not None:
            q += f" AND id IN ({','.join('?' * len(st['table_ids']))})"
            args += st["table_ids"]
        tables = rows(conn.execute(q + " ORDER BY number", args))
        for t in tables:
            s = m._active_session(conn, t["id"])
            if not s:
                t["session"] = None
                continue
            orders = [{"id": o["id"], "status": o["status"], "created_at": o["created_at"], "accepted_by": o.get("accepted_by", ""),
                       "items": [{"name": i["name"], "qty": i["qty"]} for i in o["items"]]}
                      for o in m._orders_with_items(conn, s["id"]) if o["status"] not in ("REJECTED",)]
            t["session"] = {"id": s["id"], "status": s["status"], "started_at": s["started_at"], "approved_by": s.get("approved_by", ""),
                            "guests": conn.execute("SELECT COUNT(*) FROM session_guests WHERE session_id = ?", (s["id"],)).fetchone()[0],
                            "orders": orders, "pending_count": sum(1 for o in orders if o["status"] == "PENDING"),
                            "waiter_calls": rows(conn.execute("SELECT id, reason, created_at FROM waiter_calls WHERE session_id = ? AND done = 0", (s["id"],)))}
        numbers = [t["number"] for t in tables]
        ann = rows(conn.execute(
            f"SELECT id, table_number, event_type, text_kn, text_en, created_at FROM announcements WHERE restaurant_id = ? AND created_at >= ? "
            f"AND event_type IN ('start', 'order', 'waiter', 'bill') AND table_number IN ({','.join('?' * len(numbers)) or 'NULL'}) ORDER BY id",
            (st["restaurant_id"], features._ago_iso(120), *numbers))) if numbers else []
    return {"me": {"name": st["name"], "role": st["role"]}, "restaurant": r, "tables": tables, "announcements": ann,
            "features": {"seats": config.FEATURE_SEATS, "kannada_alerts": config.FEATURE_KANNADA_ALERTS,
                         "merge_tables": config.FEATURE_MERGE_TABLES}, "server_time": now_iso()}


# ===================================================================== merge two tables (big groups)

from .db import BILL_REQUESTED, CLOSED, OPEN, PAID, WAITING_APPROVAL  # noqa: E402


def merge_info(conn, t: dict) -> dict:
    """Seats of the whole group and the numbers of tables merged into this host table."""
    if not config.FEATURE_MERGE_TABLES:
        return {"seats": t["seats"], "merged": []}
    others = rows(conn.execute("SELECT number, seats FROM tables WHERE merged_into = ? AND active = 1 ORDER BY number", (t["id"],)))
    return {"seats": t["seats"] + sum(o["seats"] for o in others), "merged": [o["number"] for o in others]}


def _merge_tables(conn, who: dict, ids) -> list[dict]:
    if not config.FEATURE_MERGE_TABLES:
        _off()
    out = []
    for tid in ids:
        t = row(conn.execute("SELECT * FROM tables WHERE id = ? AND active = 1", (tid,)).fetchone())
        if t is None:
            raise HTTPError(404, "Table not found")
        if t["restaurant_id"] != who["restaurant_id"]:
            raise HTTPError(403 if not who["is_owner"] else 404, "Table not found")
        if who["table_ids"] is not None and t["id"] not in who["table_ids"]:
            raise HTTPError(403, "This table isn't assigned to you.")
        out.append(t)
    return out


@route("POST", "/api/tables/merge")
def merge_tables(req: Request):
    """Merge `table_id` into `host_table_id`: its QR opens the host's order. If it already has guests, they and their
    orders move to the host's order (one bill). Undone with /unmerge or automatically when the host table is freed."""
    who = actor(req)
    d = req.json()
    try:
        host_id, other_id = int(d.get("host_table_id")), int(d.get("table_id"))
    except (TypeError, ValueError):
        raise HTTPError(400, "Pick two tables")
    if host_id == other_id:
        raise HTTPError(400, "Pick two different tables")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        host, other = _merge_tables(conn, who, (host_id, other_id))
        if host["merged_into"]:
            raise HTTPError(409, f"Table {host['number']} is already merged into another table.")
        if other["merged_into"]:
            raise HTTPError(409, f"Table {other['number']} is already merged.")
        if conn.execute("SELECT 1 FROM tables WHERE merged_into = ?", (other["id"],)).fetchone():
            raise HTTPError(409, f"Other tables are merged into Table {other['number']}. Unmerge them first.")
        hs, os_ = m._active_session(conn, host["id"]), m._active_session(conn, other["id"])
        if os_:
            if not hs:
                raise HTTPError(409, f"Table {other['number']} is already ordering. Pick it as the main table instead.")
            if hs["status"] not in (OPEN, WAITING_APPROVAL) or os_["status"] not in (OPEN, WAITING_APPROVAL):
                raise HTTPError(409, "Can't merge a table whose bill is requested or paid.")
            if conn.execute("SELECT 1 FROM payments WHERE session_id IN (?, ?) AND status = 'ACTIVE'", (hs["id"], os_["id"])).fetchone():
                raise HTTPError(409, "A payment is in progress. Try again after it finishes.")
            for tbl in ("session_guests", "orders", "waiter_calls"):  # one group, one bill
                conn.execute(f"UPDATE {tbl} SET session_id = ? WHERE session_id = ?", (hs["id"], os_["id"]))
            conn.execute("UPDATE table_sessions SET status = ?, closed_at = ? WHERE id = ?", (CLOSED, now_iso(), os_["id"]))
        conn.execute("UPDATE tables SET merged_into = ? WHERE id = ?", (host["id"], other["id"]))
    return {"ok": True, "host": host["number"], "merged": other["number"]}


@route("POST", "/api/tables/{table_id:int}/unmerge")
def unmerge_table(req: Request, table_id: int):
    who = actor(req)
    with db() as conn:
        (t,) = _merge_tables(conn, who, (table_id,))
        conn.execute("UPDATE tables SET merged_into = NULL WHERE id = ?", (t["id"],))
    return {"ok": True}


# ===================================================================== daily report (CSV + printable PDF)

import csv  # noqa: E402
import io  # noqa: E402

from .web import Response  # noqa: E402


def _report(conn, rid: int, date_str) -> dict:
    from . import upgrades
    s = upgrades.restaurant_sales(conn, rid, date_str, top_n=10_000)
    totals: dict[str, list] = {}
    for it in s.pop("_items"):
        t = totals.setdefault(it["name"], [0, 0])
        t[0] += int(it["qty"])
        t[1] += int(it["qty"]) * int(it["unit_price_paise"])
    items = sorted(({"name": n, "qty": q, "amount_paise": a} for n, (q, a) in totals.items()), key=lambda x: (-x["amount_paise"], x["name"]))
    r = row(conn.execute("SELECT name FROM restaurants WHERE id = ?", (rid,)).fetchone())
    return {"restaurant": r["name"], "date": s["date"], "summary": {k: s[k] for k in ("collected_paise", "bills", "average_paise", "online_paise",
            "cash_paise", "online_count", "cash_count")}, "items": items, "bills": s["bill_list"], "generated_at": now_iso()}


def _report_owner(req: Request) -> dict:
    owner = m.require_owner(req)
    if not config.FEATURE_DAILY_REPORT:
        _off()
    return owner


@route("GET", "/api/owner/report")
def report_json(req: Request):
    owner = _report_owner(req)
    with db() as conn:
        return _report(conn, owner["restaurant_id"], req.query.get("date"))


@route("GET", "/api/owner/report.csv")
def report_csv(req: Request):
    owner = _report_owner(req)
    with db() as conn:
        rep = _report(conn, owner["restaurant_id"], req.query.get("date"))
    rs = lambda p: f"{p / 100:.2f}"  # noqa: E731
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"{rep['restaurant']} - daily report", rep["date"]])
    sm = rep["summary"]
    w.writerows([[], ["Summary"], ["Collected (Rs)", rs(sm["collected_paise"])], ["Bills", sm["bills"]], ["Average bill (Rs)", rs(sm["average_paise"])],
                 ["Online / UPI (Rs)", rs(sm["online_paise"]), f"{sm['online_count']} bills"], ["Cash (Rs)", rs(sm["cash_paise"]), f"{sm['cash_count']} bills"],
                 [], ["Bills"], ["Time (IST)", "Table", "Amount (Rs)", "Method", "Cashfree link"]])
    for b in rep["bills"]:
        w.writerow([b["time"], b["table"], rs(b["amount_paise"]), b["method"], b.get("link_id") or ""])
    w.writerows([[], ["Items sold"], ["Item", "Qty", "Amount (Rs)"]])
    for i in rep["items"]:
        w.writerow([i["name"], i["qty"], rs(i["amount_paise"])])
    data = "﻿" + buf.getvalue()  # BOM so Excel opens Kannada/₹ correctly
    return Response(data.encode("utf-8"), 200, "text/csv; charset=utf-8",
                    {"Content-Disposition": f'attachment; filename="report-{rep["date"]}.csv"', "Cache-Control": "no-store"})


@route("GET", "/owner/report")
def report_page(req: Request):
    if not config.FEATURE_DAILY_REPORT:
        _off()
    return file_response(config.STATIC_DIR / "pages" / "report.html")
