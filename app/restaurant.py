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
