"""Part A restaurant upgrades (each behind a switch):

A1 Sales summary   FEATURE_SALES_SUMMARY  GET /api/dashboard/summary?date=YYYY-MM-DD
A2 Split the bill  FEATURE_SPLIT_BILL     one Cashfree link per share; table PAID only when every share is
A3 Owner voice     FEATURE_OWNER_VOICE    "today's sales?" / "mark masala dosa finished" (commands need a confirm)

Rules: numbers come from the database and code; the AI only classifies requests, translates and speaks.
"""
import secrets
from datetime import datetime, timedelta, timezone

from . import ai, cashfree, config, features
from . import main as m
from .db import BILL_REQUESTED, BILLABLE_ORDER_STATUSES, CLOSED, OPEN, PAID, PAID_CASH, PENDING, db, now_iso, row, rows
from .split import split_by_items, split_equal
from .summary import summarize
from .web import HTTPError, Request

route = m.app.route
IST = timezone(timedelta(hours=5, minutes=30))
DONE_SHARE = ("PAID", "CASH", "ZERO")


def _off():
    raise HTTPError(404, "Not found")


def _rs(paise: int) -> str:
    return f"₹{paise // 100:,}" if paise % 100 == 0 else f"₹{paise / 100:,.2f}"


def ist_day_bounds(date_str: str | None) -> tuple[str, str, str]:
    """'YYYY-MM-DD' (IST) -> (start_utc_iso, end_utc_iso, date_str)."""
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=IST)
        except ValueError:
            raise HTTPError(400, "Date must look like 2026-11-21")
    else:
        d = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    start = d.astimezone(timezone.utc)
    return start.isoformat(timespec="seconds"), (start + timedelta(days=1)).isoformat(timespec="seconds"), d.strftime("%Y-%m-%d")


def _ist_hhmm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(IST).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


# ===================================================================== A1. sales summary

METHOD = {"ONLINE": "online", "CASH": "cash", "SPLIT": "split"}


def restaurant_sales(conn, restaurant_id: int, date_str: str | None = None) -> dict:
    start, end, day = ist_day_bounds(date_str)
    sess = rows(conn.execute(
        "SELECT s.id, s.settled_paise, s.settled_at, s.pay_method, t.number FROM table_sessions s JOIN tables t ON t.id = s.table_id "
        "WHERE t.restaurant_id = ? AND s.settled_at >= ? AND s.settled_at < ? AND s.settled_paise > 0 AND s.status IN (?, ?, ?)",
        (restaurant_id, start, end, PAID, PAID_CASH, CLOSED)))
    bills, items = [], []
    for s in sess:
        links = [r[0] for r in conn.execute("SELECT link_id FROM payments WHERE session_id = ? AND status = 'PAID'", (s["id"],))]
        links += [r[0] for r in conn.execute("SELECT link_id FROM bill_shares WHERE session_id = ? AND status = 'PAID' AND cancelled = 0", (s["id"],))]
        bills.append({"session_id": s["id"], "table": s["number"], "amount_paise": s["settled_paise"],
                      "method": METHOD.get(s["pay_method"], "online"), "link_id": ", ".join(x for x in links if x) or None,
                      "settled_at": s["settled_at"], "time": _ist_hhmm(s["settled_at"])})
        items += rows(conn.execute(
            "SELECT oi.name, oi.qty, oi.unit_price_paise FROM order_items oi JOIN orders o ON o.id = oi.order_id "
            f"WHERE o.session_id = ? AND o.status IN ({','.join('?' * len(BILLABLE_ORDER_STATUSES))})",
            (s["id"], *BILLABLE_ORDER_STATUSES)))
    out = summarize(bills, items)
    out["date"] = day
    return out


@route("GET", "/api/dashboard/summary")
def sales_summary(req: Request):
    owner = m.require_owner(req)
    if not config.FEATURE_SALES_SUMMARY:
        _off()
    with db() as conn:
        biz = conn.execute("SELECT business_type FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()[0]
        if biz == "supermarket":
            from . import store
            return store.store_sales(conn, owner["restaurant_id"], req.query.get("date"))
        return restaurant_sales(conn, owner["restaurant_id"], req.query.get("date"))


# ===================================================================== A2. split the bill

def split_active(conn, session_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM bill_shares WHERE session_id = ? AND cancelled = 0", (session_id,)).fetchone())


def _shares(conn, session_id: int) -> list[dict]:
    return rows(conn.execute("SELECT * FROM bill_shares WHERE session_id = ? AND cancelled = 0 ORDER BY id", (session_id,)))


def split_summary(conn, session_id: int):
    sh = _shares(conn, session_id)
    if not sh:
        return None
    done = [s for s in sh if s["status"] in DONE_SHARE]
    return {"mode": sh[0]["mode"], "total": len(sh), "paid": len(done),
            "pending_paise": sum(s["amount_paise"] for s in sh if s["status"] not in DONE_SHARE),
            "shares": [{"id": s["id"], "label": s["label"], "amount_paise": s["amount_paise"], "status": s["status"]} for s in sh]}


def _bill_lines(conn, session_id: int) -> list[dict]:
    return rows(conn.execute(
        "SELECT oi.id, oi.name, oi.qty, oi.unit_price_paise, oi.qty * oi.unit_price_paise AS amount_paise, o.guest_id AS payer "
        "FROM order_items oi JOIN orders o ON o.id = oi.order_id "
        f"WHERE o.session_id = ? AND o.status IN ({','.join('?' * len(BILLABLE_ORDER_STATUSES))}) ORDER BY oi.id",
        (session_id, *BILLABLE_ORDER_STATUSES)))


def _my_guest_id(conn, req: Request):
    g = conn.execute("SELECT id FROM session_guests WHERE token = ?", (req.header("X-Guest-Token") or "",)).fetchone()
    return g["id"] if g else None


def make_split(conn, s: dict, mode: str, n: int | None, shared_item_ids, my_guest) -> None:
    """Create shares for a BILL_REQUESTED session. Shares always sum exactly to the bill."""
    if s["status"] != BILL_REQUESTED:
        raise HTTPError(409, "Request the bill first, then split it.")
    if any(x["status"] in ("PAID", "CASH") for x in _shares(conn, s["id"])):
        raise HTTPError(409, "Someone has already paid a share, so the split can't change now.")
    total = m._bill_paise(conn, s["id"])
    if total <= 0:
        raise HTTPError(409, "There's nothing to split yet.")
    plan = []  # (label, guest_id, amount)
    if mode == "equal":
        if not isinstance(n, int) or not 2 <= n <= 20:
            raise HTTPError(400, "Split between 2 and 20 people.")
        plan = [(f"Share {i + 1} of {n}", None, amt) for i, amt in enumerate(split_equal(total, n))]
    elif mode == "items":
        guests = [r["id"] for r in conn.execute("SELECT id FROM session_guests WHERE session_id = ? ORDER BY id", (s["id"],))]
        if len(guests) < 2:
            raise HTTPError(409, "Only one phone has joined this table. Use an equal split, or ask friends to join with the code.")
        lines = _bill_lines(conn, s["id"])
        valid = {l["id"] for l in lines}
        shared = [int(i) for i in (shared_item_ids or []) if str(i).isdigit() and int(i) in valid]
        amounts = split_by_items(lines, guests, shared)
        plan = [(f"Phone {i + 1}", g, amounts[g]) for i, g in enumerate(guests)]
    else:
        raise HTTPError(400, "Choose an equal split or split by items.")
    assert sum(a for _, _, a in plan) == total
    old = [x["link_id"] for x in _shares(conn, s["id"]) if x["link_id"]]
    conn.execute("UPDATE bill_shares SET cancelled = 1 WHERE session_id = ? AND cancelled = 0", (s["id"],))
    for label, guest, amt in plan:
        conn.execute("INSERT INTO bill_shares (session_id, label, guest_id, amount_paise, status, mode, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)", (s["id"], label, guest, amt, "ZERO" if amt == 0 else "PENDING", mode, now_iso()))
    for link_id in old:
        cashfree.cancel_link(link_id)


def _split_view(conn, s: dict, me) -> dict:
    sh = _shares(conn, s["id"])
    lines = _bill_lines(conn, s["id"])
    return {
        "status": s["status"], "bill_paise": m._bill_paise(conn, s["id"]),
        "guests": conn.execute("SELECT COUNT(*) FROM session_guests WHERE session_id = ?", (s["id"],)).fetchone()[0],
        "lines": [{"id": l["id"], "name": l["name"], "qty": l["qty"], "amount_paise": l["amount_paise"], "mine": l["payer"] == me}
                  for l in lines],
        "shares": [{"id": x["id"], "label": x["label"] + (" (you)" if me and x["guest_id"] == me else ""),
                    "amount_paise": x["amount_paise"], "status": x["status"], "mine": bool(me and x["guest_id"] == me),
                    "has_link": bool(x["link_id"])} for x in sh],
        "summary": split_summary(conn, s["id"]),
        "can_change": bool(not sh or not any(x["status"] in ("PAID", "CASH") for x in sh)),
    }


@route("GET", "/api/session/{session_id:int}/split")
def split_get(req: Request, session_id: int):
    if not config.features()["split_bill"]:
        _off()
    refresh_shares(session_id)
    with db() as conn:
        s = m._guest_session(conn, session_id, req)
        return _split_view(conn, s, _my_guest_id(conn, req))


@route("POST", "/api/session/{session_id:int}/split")
def split_create(req: Request, session_id: int):
    if not config.features()["split_bill"]:
        _off()
    d = req.json()
    mode = str(d.get("mode") or "")
    try:
        n = int(d["n"]) if d.get("n") is not None else None
    except (TypeError, ValueError):
        n = None
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = m._guest_session(conn, session_id, req)
        make_split(conn, s, mode, n, d.get("shared_item_ids") or [], _my_guest_id(conn, req))
        return _split_view(conn, s, _my_guest_id(conn, req))


@route("POST", "/api/session/{session_id:int}/split/cancel")
def split_cancel(req: Request, session_id: int):
    if not config.features()["split_bill"]:
        _off()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = m._guest_session(conn, session_id, req)
        sh = _shares(conn, session_id)
        if any(x["status"] in ("PAID", "CASH") for x in sh):
            raise HTTPError(409, "Someone has already paid a share, so the split can't be undone.")
        conn.execute("UPDATE bill_shares SET cancelled = 1 WHERE session_id = ? AND cancelled = 0", (session_id,))
        links = [x["link_id"] for x in sh if x["link_id"]]
        view = _split_view(conn, s, _my_guest_id(conn, req))
    for l in links:
        cashfree.cancel_link(l)
    return view


@route("POST", "/api/session/{session_id:int}/shares/{share_id:int}/pay")
def share_pay(req: Request, session_id: int, share_id: int):
    if not config.features()["split_bill"]:
        _off()
    phone = m._valid_phone(str(req.json().get("phone") or ""))
    refresh_shares(session_id)
    with db() as conn:
        s = m._guest_session(conn, session_id, req)
        x = row(conn.execute("SELECT * FROM bill_shares WHERE id = ? AND session_id = ? AND cancelled = 0",
                             (share_id, session_id)).fetchone())
        if x is None:
            raise HTTPError(404, "That share isn't part of this bill any more.")
        if x["status"] in DONE_SHARE:
            raise HTTPError(409, "This share is already paid.")
        if s["status"] != BILL_REQUESTED:
            raise HTTPError(409, "This bill can't be paid right now.")
        restaurant = conn.execute("SELECT name FROM restaurants WHERE id = ?", (s["restaurant_id"],)).fetchone()["name"]
        conn.execute("UPDATE bill_shares SET phone = ? WHERE id = ?", (phone, share_id))
    if x["status"] == "ACTIVE" and x["link_url"] and x["expires_at"] > now_iso():
        return {"link_url": x["link_url"], "amount_paise": x["amount_paise"]}
    link_id = f"bd{session_id}_{share_id}_{x['link_count'] + 1}{secrets.token_hex(2)}"
    base = m.public_base(req)
    try:
        link = cashfree.create_link(link_id, x["amount_paise"], phone,
                                    f"{restaurant} - Table {s['table_number']} - {x['label']}",
                                    return_url=f"{base}/paid?session={session_id}&share={share_id}",
                                    notify_url=f"{base}/api/webhooks/cashfree")
    except cashfree.CashfreeError as e:
        raise HTTPError(502, str(e))
    expires = (datetime.now(timezone.utc) + timedelta(minutes=29)).isoformat(timespec="seconds")
    with db() as conn:
        conn.execute("UPDATE bill_shares SET link_id = ?, link_url = ?, link_count = link_count + 1, expires_at = ?, "
                     "status = 'ACTIVE' WHERE id = ? AND status NOT IN ('PAID', 'CASH', 'ZERO')",
                     (link_id, link["link_url"], expires, share_id))
    return {"link_url": link["link_url"], "amount_paise": x["amount_paise"]}


def _complete_if_all_paid(conn, session_id: int) -> None:
    sh = _shares(conn, session_id)
    if not sh or any(x["status"] not in DONE_SHARE for x in sh):
        return
    total = sum(x["amount_paise"] for x in sh)
    ts = now_iso()
    cur = conn.execute("UPDATE table_sessions SET status = ?, settled_paise = ?, settled_at = ?, pay_method = 'SPLIT' "
                       "WHERE id = ? AND status = ?", (PAID, total, ts, session_id, BILL_REQUESTED))
    if cur.rowcount:
        w = conn.execute("SELECT t.restaurant_id, t.number FROM table_sessions s JOIN tables t ON t.id = s.table_id WHERE s.id = ?",
                         (session_id,)).fetchone()
        features.announce(conn, w["restaurant_id"], w["number"], "paid", amount_paise=total)


def check_share_link(link_id: str) -> str:
    """Ask Cashfree about a share's link and record it. Idempotent. Returns the share status or 'UNKNOWN'."""
    with db() as conn:
        x = row(conn.execute("SELECT * FROM bill_shares WHERE link_id = ?", (link_id,)).fetchone())
    if x is None:
        return "UNKNOWN"
    if x["status"] in DONE_SHARE:
        return x["status"]
    try:
        link = cashfree.get_link(link_id)
    except cashfree.CashfreeError:
        return x["status"]
    if cashfree.is_paid(link, x["amount_paise"]):
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("UPDATE bill_shares SET status = 'PAID', paid_at = ? WHERE id = ? AND status NOT IN ('PAID', 'CASH', 'ZERO')",
                               (now_iso(), x["id"]))
            if cur.rowcount:
                w = conn.execute("SELECT t.restaurant_id, t.number FROM table_sessions s JOIN tables t ON t.id = s.table_id "
                                 "WHERE s.id = ?", (x["session_id"],)).fetchone()
                features.announce(conn, w["restaurant_id"], w["number"], "share_paid", amount_paise=x["amount_paise"])
                _complete_if_all_paid(conn, x["session_id"])
        return "PAID"
    status = str(link.get("link_status", "")).upper()
    if status in ("EXPIRED", "CANCELLED") and x["status"] == "ACTIVE":
        with db() as conn:
            conn.execute("UPDATE bill_shares SET status = 'EXPIRED' WHERE id = ? AND status = 'ACTIVE'", (x["id"],))
        return "EXPIRED"
    return x["status"]


def refresh_shares(session_id: int) -> None:
    with db() as conn:
        links = [r[0] for r in conn.execute("SELECT link_id FROM bill_shares WHERE session_id = ? AND cancelled = 0 "
                                            "AND status = 'ACTIVE' AND link_id IS NOT NULL", (session_id,))]
    for l in links:
        check_share_link(l)


def check_other_link(link_id: str) -> None:
    """Webhook for a link that isn't a whole-bill link: a split share, or a supermarket order."""
    if check_share_link(link_id) == "UNKNOWN":
        from . import store
        store.check_order_link(link_id)


def cash_remaining_shares(conn, session_id: int) -> None:
    conn.execute("UPDATE bill_shares SET status = 'CASH' WHERE session_id = ? AND cancelled = 0 AND status NOT IN ('PAID', 'ZERO')",
                 (session_id,))


@route("POST", "/api/shares/{share_id:int}/cash")
def share_cash(req: Request, share_id: int):
    owner = m.require_owner(req)
    if not config.features()["split_bill"]:
        _off()
    x = None
    with db() as conn:
        x = row(conn.execute("SELECT * FROM bill_shares WHERE id = ? AND cancelled = 0", (share_id,)).fetchone())
        if x is None:
            raise HTTPError(404, "Share not found")
        m._owner_session(conn, x["session_id"], owner)
    if x["link_id"] and check_share_link(x["link_id"]) == "PAID":
        raise HTTPError(409, "This share was just paid online.")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE bill_shares SET status = 'CASH', paid_at = ? WHERE id = ? AND status NOT IN ('PAID', 'CASH', 'ZERO')",
                     (now_iso(), share_id))
        _complete_if_all_paid(conn, x["session_id"])
    if x["link_id"]:
        cashfree.cancel_link(x["link_id"])
    return {"ok": True}


def dashboard_extras(conn, restaurant_id: int) -> dict:
    out = {"splits": {}}
    if config.FEATURE_SPLIT_BILL:
        for r in rows(conn.execute(
                "SELECT b.session_id, COUNT(*) AS total, SUM(b.status IN ('PAID','CASH','ZERO')) AS paid, "
                "SUM(CASE WHEN b.status IN ('PAID','CASH','ZERO') THEN 0 ELSE b.amount_paise END) AS pending "
                "FROM bill_shares b JOIN table_sessions s ON s.id = b.session_id JOIN tables t ON t.id = s.table_id "
                "WHERE t.restaurant_id = ? AND b.cancelled = 0 AND s.status IN (?, ?, ?) GROUP BY b.session_id",
                (restaurant_id, OPEN, BILL_REQUESTED, PAID))):
            sh = rows(conn.execute("SELECT id, label, amount_paise, status FROM bill_shares WHERE session_id = ? AND cancelled = 0 "
                                   "ORDER BY id", (r["session_id"],)))
            out["splits"][str(r["session_id"])] = {"total": r["total"], "paid": r["paid"], "pending_paise": r["pending"], "shares": sh}
    return out


# ===================================================================== A3. owner voice assistant

OWNER_PROMPT = """A restaurant owner asks a question or gives a command (Kannada, Hindi, English or mixed).
Reply with ONE JSON object only:
{"intent": "sales_today"|"orders_count"|"top_items"|"waiting_tables"|"pending_payments"|"settlement_status"|"mark_item_unavailable"|"mark_item_available"|"free_table"|"unknown",
 "item": string|null, "table": integer|null}
Menu items: {MENU_NAMES}. Never answer the question yourself; only classify it."""

HELP = "I can tell you today's sales, top items, waiting tables, or mark an item finished."


def _orders_today(conn, rid: int) -> dict:
    start, _, _ = ist_day_bounds(None)
    r = conn.execute("SELECT COUNT(*) AS n, SUM(o.status = ?) AS pending FROM orders o JOIN table_sessions s ON s.id = o.session_id "
                     "JOIN tables t ON t.id = s.table_id WHERE t.restaurant_id = ? AND o.created_at >= ? AND o.status != 'REJECTED'",
                     (PENDING, rid, start)).fetchone()
    return {"n": r["n"] or 0, "pending": r["pending"] or 0}


def _waiting(conn, rid: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for r in rows(conn.execute(
            "SELECT t.number, MIN(o.created_at) AS since FROM orders o JOIN table_sessions s ON s.id = o.session_id "
            "JOIN tables t ON t.id = s.table_id WHERE t.restaurant_id = ? AND o.status IN ('ACCEPTED', 'PREPARING') "
            "AND s.status IN (?, ?, ?) GROUP BY t.number", (rid, OPEN, BILL_REQUESTED, PAID))):
        mins = max(0, int((now - datetime.fromisoformat(r["since"])).total_seconds() // 60))
        out.append({"table": r["number"], "minutes": mins})
    return sorted(out, key=lambda x: -x["minutes"])


def _pending_payments(conn, rid: int) -> list[dict]:
    out = []
    for s in rows(conn.execute("SELECT s.id, t.number FROM table_sessions s JOIN tables t ON t.id = s.table_id "
                               "WHERE t.restaurant_id = ? AND s.status = ?", (rid, BILL_REQUESTED))):
        sp = split_summary(conn, s["id"])
        out.append({"table": s["number"], "pending_paise": sp["pending_paise"] if sp else m._bill_paise(conn, s["id"])})
    return out


def owner_answer(conn, rid: int, data: dict, menu: list[dict]) -> tuple[str, dict | None]:
    """Run ONE classified intent with code and return (fixed English answer with real numbers, confirm-or-None)."""
    intent = str(data.get("intent") or "unknown")
    if intent == "sales_today":
        s = restaurant_sales(conn, rid)
        if not s["bills"]:
            return "No bills have been paid yet today.", None
        return (f"Today you've collected {_rs(s['collected_paise'])} from {s['bills']} bill{'s' if s['bills'] != 1 else ''}. "
                f"Online {_rs(s['online_paise'])}, cash {_rs(s['cash_paise'])}."), None
    if intent == "orders_count":
        o = _orders_today(conn, rid)
        return f"{o['n']} order{'s' if o['n'] != 1 else ''} today. {o['pending']} waiting for you to accept.", None
    if intent == "top_items":
        top = restaurant_sales(conn, rid)["top_items"]
        if not top:
            return "Nothing has been sold yet today.", None
        return "Top items today: " + ", ".join(f"{t['name']} ({t['qty']})" for t in top) + ".", None
    if intent == "waiting_tables":
        w = _waiting(conn, rid)
        if not w:
            return "No table is waiting for food right now.", None
        return "Waiting for food: " + ", ".join(f"table {x['table']} for {x['minutes']} minute{'s' if x['minutes'] != 1 else ''}" for x in w[:5]) + ".", None
    if intent == "pending_payments":
        p = _pending_payments(conn, rid)
        if not p:
            return "No table is waiting to pay.", None
        return (f"{len(p)} table{'s' if len(p) != 1 else ''} waiting to pay: "
                + ", ".join(f"table {x['table']} {_rs(x['pending_paise'])}" for x in p) + "."), None
    if intent == "settlement_status":
        st = cashfree.latest_settlement()
        if not st:
            return "Settlement details aren't available yet.", None
        return f"Your last Cashfree settlement was {_rs(st['amount_paise'])} on {st['date']}.", None
    if intent in ("mark_item_unavailable", "mark_item_available"):
        item = features.find_menu_item(str(data.get("item") or ""), menu)
        if not item:
            return "I couldn't find that dish on the menu. Please say its name again.", None
        want = intent == "mark_item_available"
        if bool(item["available"]) == want:
            return f"{item['name']} is already marked {'available' if want else 'finished'}.", None
        return (f"Mark {item['name']} as {'available again' if want else 'finished for today'}?",
                {"action": intent, "item_id": item["id"], "label": item["name"]})
    if intent == "free_table":
        try:
            n = int(data.get("table"))
        except (TypeError, ValueError):
            return "Which table should I free? Say the table number.", None
        t = conn.execute("SELECT id FROM tables WHERE restaurant_id = ? AND number = ? AND active = 1", (rid, n)).fetchone()
        s = m._active_session(conn, t["id"]) if t else None
        if not s:
            return f"Table {n} is already free.", None
        return f"Free table {n} and end its session?", {"action": "free_table", "session_id": s["id"], "label": f"Table {n}"}
    return HELP, None


@route("POST", "/api/owner/voice")
def owner_voice(req: Request):
    owner = m.require_owner(req)
    if not config.features()["owner_voice"]:
        _off()
    fields, files = req.form()
    audio = files.get("audio")
    text = (fields.get("text") or "").strip()[:300]
    with db() as conn:
        lang = conn.execute("SELECT language FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()[0]
        menu = m._menu(conn, owner["restaurant_id"])
    if audio is not None and audio.data:
        try:
            transcript = ai.stt(audio.data, audio.filename or "voice.wav", audio.content_type or "audio/wav", None)["transcript"]
        except ai.AIError:
            return {"transcript": "", "answer": "I couldn't hear that. Please try again or type your question.", "answer_en": "", "audio": None, "confirm": None}
    elif text:
        transcript = text
    else:
        raise HTTPError(400, "Say or type a question.")
    try:
        data = ai.chat_json([{"role": "system", "content": OWNER_PROMPT.replace("{MENU_NAMES}", "; ".join(i["name"] for i in menu))},
                             {"role": "user", "content": transcript}])
    except ai.AIError:
        return {"transcript": transcript, "answer": "Sorry, I can't answer right now. The dashboard numbers are up to date.", "answer_en": "", "audio": None, "confirm": None}
    with db() as conn:
        answer_en, confirm = owner_answer(conn, owner["restaurant_id"], data if isinstance(data, dict) else {}, menu)
    answer, audio_out = features._localise(answer_en, lang)
    return {"transcript": transcript, "intent": (data or {}).get("intent"), "answer": answer, "answer_en": answer_en,
            "audio": audio_out, "confirm": confirm}


@route("POST", "/api/owner/voice/confirm")
def owner_voice_confirm(req: Request):
    owner = m.require_owner(req)
    if not config.features()["owner_voice"]:
        _off()
    d = req.json()
    action = d.get("action")
    if action in ("mark_item_unavailable", "mark_item_available"):
        with db() as conn:
            cur = conn.execute("UPDATE menu_items SET available = ? WHERE id = ? AND restaurant_id = ? AND deleted = 0",
                               (1 if action == "mark_item_available" else 0, int(d.get("item_id") or 0), owner["restaurant_id"]))
            if not cur.rowcount:
                raise HTTPError(404, "Dish not found")
        return {"ok": True, "message": "Done. The menu is updated."}
    if action == "free_table":
        m.cashier_free(req, int(d.get("session_id") or 0))  # the same rules as the Free table button
        return {"ok": True, "message": "Done. The table is free."}
    raise HTTPError(400, "Unknown action")
