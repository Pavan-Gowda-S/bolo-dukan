"""Table games that matter to the bill: Bill Roulette (5a), Housie / tambola (5b), Lucky Spin (5c).

Rules (same as the rest of the app):
- Every random result is drawn on the server (`secrets`), never on a phone, so nobody can rig it.
- Prizes are free menu items added at ₹0 by staff with one tap ("Give free juice"), like the quiz's free tea.
  Nothing changes money by itself.
- Each game has its own switch: FEATURE_ROULETTE, FEATURE_HOUSIE, FEATURE_LUCKY_SPIN.
"""
import json
import re
import secrets
import time

from . import config, features
from . import main as m
from .budget import kind_of
from .db import ACCEPTED, ACTIVE_SESSION_STATUSES, BILL_REQUESTED, OPEN, PAID, db, now_iso, row, rows
from .web import HTTPError, Request

route = m.app.route
rng = secrets.SystemRandom()


def _off():
    raise HTTPError(404, "Not found")


def _playing_session(conn, session_id: int, req: Request) -> dict:
    s = m._guest_session(conn, session_id, req)
    if s["status"] not in (OPEN, BILL_REQUESTED, PAID):
        raise HTTPError(409, "Games open once your table is approved.")
    return s


# ===================================================================== shared prizes (free item at ₹0, given by staff)

PRIZE_ITEMS = {  # kind -> (words to look for in the menu, the budget.kind_of fallback)
    "juice": (r"juice|lime|soda|lassi|buttermilk|majjige|shake", "drink"),
    "chai": (r"masala chai|\bchai\b|\btea\b|coffee|kaapi", "drink"),
    "dessert": (r"jamun|payasa|kheer|halwa|ice ?cream|kulfi|mysore pak|sweet|dessert", "dessert"),
    "starter": (r"starter|soup|vada|bajji|bonda|pakora|samosa|tikka|65\b|chaat", "starter"),
}


def award_prize(conn, session: dict, game: str, kind: str, label: str) -> int:
    """Record a pending prize and tell the dashboard (Kannada alert from a fixed phrase)."""
    pid = conn.execute(
        "INSERT INTO game_prizes (restaurant_id, session_id, table_number, game, kind, label, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (session["restaurant_id"], session["id"], session["table_number"], game, kind, label, now_iso())).lastrowid
    features.announce(conn, session["restaurant_id"], session["table_number"], "game_prize", reason=label)
    return pid


def pending_prizes(conn, restaurant_id: int) -> list[dict]:
    return rows(conn.execute(
        "SELECT p.id, p.table_number, p.game, p.kind, p.label, p.created_at FROM game_prizes p "
        "JOIN table_sessions s ON s.id = p.session_id WHERE p.restaurant_id = ? AND p.status = 'pending' "
        "AND s.status IN (?, ?, ?) ORDER BY p.id", (restaurant_id, OPEN, BILL_REQUESTED, PAID)))


def _prize_item(menu: list[dict], kind: str):
    words, fallback = PRIZE_ITEMS.get(kind, ("", "other"))
    hits = [x for x in menu if words and re.search(words, x["name"] + " " + x["category"], re.I)]
    hits = hits or [x for x in menu if kind_of(x["category"], x["name"]) == fallback]
    return min(hits, key=lambda x: x["price_paise"], default=None)


@route("POST", "/api/prizes/{prize_id:int}/give")
def give_prize(req: Request, prize_id: int):
    """Owner or waiter taps 'Give': the cheapest matching menu item is added to the table's bill at ₹0."""
    from . import restaurant
    who = restaurant.actor(req)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        p = row(conn.execute("SELECT * FROM game_prizes WHERE id = ?", (prize_id,)).fetchone())
        if p is None:
            raise HTTPError(404, "Prize not found")
        s = restaurant.session_for(conn, p["session_id"], who)
        if p["status"] != "pending":
            raise HTTPError(409, "This prize was already handled.")
        if s["status"] not in (OPEN, BILL_REQUESTED, PAID):
            conn.execute("UPDATE game_prizes SET status = 'void' WHERE id = ?", (prize_id,))
            return {"ok": True, "added": False, "message": "That table has left. Prize cancelled."}
        item = _prize_item(m._menu(conn, s["restaurant_id"], only_available=True), p["kind"])
        if item:
            ts = now_iso()
            oid = conn.execute("INSERT INTO orders (session_id, status, created_at, updated_at, accepted_at, accepted_by) "
                               "VALUES (?, ?, ?, ?, ?, ?)", (p["session_id"], ACCEPTED, ts, ts, ts, who["label"])).lastrowid
            conn.execute("INSERT INTO order_items (order_id, menu_item_id, name, qty, unit_price_paise) VALUES (?, ?, ?, 1, 0)",
                         (oid, item["id"], f"{item['name']} ({p['game']} prize, free)"))
        conn.execute("UPDATE game_prizes SET status = 'given', given_by = ? WHERE id = ?", (who["label"], prize_id))
    return {"ok": True, "added": bool(item),
            "message": f"Free {item['name']} added to table {p['table_number']} at ₹0." if item
            else f"Nothing like '{p['label']}' on the menu: please serve table {p['table_number']} by hand."}


# ===================================================================== 5a. Bill Roulette (who pays for the table)

def _roulette_on():
    if not config.FEATURE_ROULETTE:
        _off()


def _roulette_view(r: dict) -> dict:
    players = json.loads(r["players"])
    pulls = json.loads(r["pulls"])
    out = {"id": r["id"], "players": players, "pulls": pulls, "turn": len(pulls) % len(players) if not r["done"] else None,
           "chambers": len(players), "done": bool(r["done"])}
    if r["done"]:
        out["loser"] = players[r["loser"]]
    return out


@route("POST", "/api/session/{session_id:int}/roulette")
def roulette_start(req: Request, session_id: int):
    """Names of everyone playing (2-12). The server loads one chamber at random before anyone pulls."""
    _roulette_on()
    names = req.json().get("players")
    if not isinstance(names, list):
        raise HTTPError(400, "Add the players")
    clean = []
    for n in names:
        n = re.sub(r"\s+", " ", str(n or "")).strip()[:16]
        if n and n.lower() not in (c.lower() for c in clean):
            clean.append(n)
    if not 2 <= len(clean) <= 12:
        raise HTTPError(400, "Bill Roulette needs 2 to 12 players")
    with db() as conn:
        _playing_session(conn, session_id, req)
        rid = conn.execute("INSERT INTO roulette_rounds (session_id, players, loser, pulls, done, created_at) VALUES (?, ?, ?, '[]', 0, ?)",
                           (session_id, json.dumps(clean, ensure_ascii=False), secrets.randbelow(len(clean)), now_iso())).lastrowid
        return _roulette_view(row(conn.execute("SELECT * FROM roulette_rounds WHERE id = ?", (rid,)).fetchone()))


@route("POST", "/api/session/{session_id:int}/roulette/{round_id:int}/pull")
def roulette_pull(req: Request, session_id: int, round_id: int):
    """The next player in order pulls. Players go round in order; the loaded chamber was fixed at the start."""
    _roulette_on()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _playing_session(conn, session_id, req)
        r = row(conn.execute("SELECT * FROM roulette_rounds WHERE id = ? AND session_id = ?", (round_id, session_id)).fetchone())
        if r is None:
            raise HTTPError(404, "Game not found")
        if r["done"]:
            raise HTTPError(409, "This round is over. Start a new one.")
        players, pulls = json.loads(r["players"]), json.loads(r["pulls"])
        turn = len(pulls) % len(players)
        bang = turn == r["loser"]
        pulls.append({"player": players[turn], "bang": bang})
        conn.execute("UPDATE roulette_rounds SET pulls = ?, done = ? WHERE id = ?", (json.dumps(pulls, ensure_ascii=False), int(bang), round_id))
        if bang:
            conn.execute("UPDATE table_sessions SET bill_payer = ? WHERE id = ?", (players[turn], session_id))
            features.announce(conn, s["restaurant_id"], s["table_number"], "roulette", reason=players[turn])
        r = row(conn.execute("SELECT * FROM roulette_rounds WHERE id = ?", (round_id,)).fetchone())
        return dict(_roulette_view(r), last={"player": players[turn], "bang": bang})


# ===================================================================== 5b. Housie / tambola (whole restaurant)

HOUSIE_LOBBY, HOUSIE_EVERY = 40, 7   # seconds before the first number, seconds between numbers
HOUSIE_PRIZES = {"line": ("juice", "juice", "First line"), "full": ("starter", "starter", "Full house")}


def make_ticket(rand=None) -> list[list]:
    """A real tambola ticket: 3 rows x 9 columns, 5 numbers per row, 15 numbers, column c holds 10c..10c+9
    (1-9 in the first, 80-90 in the last), numbers ascending down each column. Empty cells are None."""
    rand = rand or rng
    ranges = [list(range(1, 10))] + [list(range(10 * c, 10 * c + 10)) for c in range(1, 8)] + [list(range(80, 91))]
    while True:
        counts = [1] * 9
        while sum(counts) < 15:
            c = rand.randrange(9)
            if counts[c] < 3:
                counts[c] += 1
        rows_used = [0, 0, 0]
        grid = [[None] * 9 for _ in range(3)]
        ok = True
        for c in sorted(range(9), key=lambda c: -counts[c]):     # place the fullest columns first
            free = sorted((r for r in range(3) if rows_used[r] < 5), key=lambda r: (rows_used[r], rand.random()))
            if len(free) < counts[c]:
                ok = False
                break
            for r in free[:counts[c]]:
                grid[r][c] = True
                rows_used[r] += 1
        if not ok or rows_used != [5, 5, 5]:
            continue
        for c in range(9):
            nums = sorted(rand.sample(ranges[c], counts[c]))
            for r in range(3):
                if grid[r][c]:
                    grid[r][c] = nums.pop(0)
        return grid


def ticket_numbers(grid) -> list[int]:
    return [n for line in grid for n in line if n]


def check_claim(grid, called: set, prize: str) -> bool:
    if prize == "line":
        return any(all(n in called for n in line if n) for line in grid)
    if prize == "full":
        return all(n in called for n in ticket_numbers(grid))
    return False


def _housie_on():
    if not config.FEATURE_HOUSIE:
        _off()


def _housie_current(conn, rid: int):
    r = row(conn.execute("SELECT * FROM housie_rounds WHERE restaurant_id = ? ORDER BY id DESC LIMIT 1", (rid,)).fetchone())
    if r and not r["ended"] and time.time() > r["starts_at"] + 90 * HOUSIE_EVERY + 60:
        conn.execute("UPDATE housie_rounds SET ended = 1 WHERE id = ?", (r["id"],))
        r["ended"] = 1
    return r


def _called(r: dict, now: float | None = None) -> list[int]:
    now = time.time() if now is None else now
    if now < r["starts_at"]:
        return []
    k = min(90, int((now - r["starts_at"]) // HOUSIE_EVERY) + 1)
    return json.loads(r["seq"])[:k]


def _housie_view(conn, r, session_id: int) -> dict:
    if r is None:
        return {"round": None}
    called = _called(r) if not r["ended"] else _called(r, r["ended_at"] or time.time())
    t = row(conn.execute("SELECT grid FROM housie_tickets WHERE round_id = ? AND session_id = ?", (r["id"], session_id)).fetchone())
    claims = rows(conn.execute("SELECT prize, table_number FROM housie_claims WHERE round_id = ? ORDER BY created_at", (r["id"],)))
    players = conn.execute("SELECT COUNT(*) FROM housie_tickets WHERE round_id = ?", (r["id"],)).fetchone()[0]
    now = time.time()
    return {"round": r["id"], "ended": bool(r["ended"]), "starts_in": max(0, round(r["starts_at"] - now, 1)),
            "next_in": round(HOUSIE_EVERY - ((now - r["starts_at"]) % HOUSIE_EVERY), 1) if now >= r["starts_at"] and not r["ended"] else None,
            "called": called, "ticket": json.loads(t["grid"]) if t else None, "tables": players,
            "claims": claims, "prizes": {k: v[2] + " → free " + v[1] for k, v in HOUSIE_PRIZES.items()}}


@route("GET", "/api/session/{session_id:int}/housie")
def housie_state(req: Request, session_id: int):
    _housie_on()
    with db() as conn:
        s = _playing_session(conn, session_id, req)
        return _housie_view(conn, _housie_current(conn, s["restaurant_id"]), session_id)


@route("POST", "/api/session/{session_id:int}/housie/join")
def housie_join(req: Request, session_id: int):
    """Join the running game, or start a new one (first number after a 40-second lobby). One ticket per table."""
    _housie_on()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _playing_session(conn, session_id, req)
        r = _housie_current(conn, s["restaurant_id"])
        if r is None or r["ended"]:
            seq = list(range(1, 91))
            rng.shuffle(seq)
            new = conn.execute("INSERT INTO housie_rounds (restaurant_id, starts_at, seq, ended, created_at) VALUES (?, ?, ?, 0, ?)",
                               (s["restaurant_id"], time.time() + HOUSIE_LOBBY, json.dumps(seq), now_iso())).lastrowid
            r = row(conn.execute("SELECT * FROM housie_rounds WHERE id = ?", (new,)).fetchone())
        if not conn.execute("SELECT 1 FROM housie_tickets WHERE round_id = ? AND session_id = ?", (r["id"], session_id)).fetchone():
            if len(_called(r)) > 30:
                raise HTTPError(409, "This game is well under way. Join the next one.")
            conn.execute("INSERT INTO housie_tickets (round_id, session_id, table_number, grid) VALUES (?, ?, ?, ?)",
                         (r["id"], session_id, s["table_number"], json.dumps(make_ticket())))
        return _housie_view(conn, r, session_id)


@route("POST", "/api/session/{session_id:int}/housie/claim")
def housie_claim(req: Request, session_id: int):
    """'Line' or 'Full house'. The server checks the ticket against the numbers really called; the first valid claim wins."""
    _housie_on()
    prize = str(req.json().get("prize") or "")
    if prize not in HOUSIE_PRIZES:
        raise HTTPError(400, "Claim 'line' or 'full'")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _playing_session(conn, session_id, req)
        r = _housie_current(conn, s["restaurant_id"])
        if r is None or r["ended"]:
            raise HTTPError(409, "There's no game running.")
        t = row(conn.execute("SELECT grid FROM housie_tickets WHERE round_id = ? AND session_id = ?", (r["id"], session_id)).fetchone())
        if t is None:
            raise HTTPError(409, "Join the game first.")
        if conn.execute("SELECT 1 FROM housie_claims WHERE round_id = ? AND prize = ?", (r["id"], prize)).fetchone():
            raise HTTPError(409, f"Someone already won {HOUSIE_PRIZES[prize][2].lower()}.")
        if not check_claim(json.loads(t["grid"]), set(_called(r)), prize):
            raise HTTPError(409, "Not yet: some of those numbers haven't been called. Keep playing.")
        conn.execute("INSERT INTO housie_claims (round_id, prize, session_id, table_number, created_at) VALUES (?, ?, ?, ?, ?)",
                     (r["id"], prize, session_id, s["table_number"], now_iso()))
        kind, item, title = HOUSIE_PRIZES[prize]
        award_prize(conn, s, "Housie", kind, f"{item} ({title})")
        if prize == "full":
            conn.execute("UPDATE housie_rounds SET ended = 1, ended_at = ? WHERE id = ?", (time.time(), r["id"]))
        r = row(conn.execute("SELECT * FROM housie_rounds WHERE id = ?", (r["id"],)).fetchone())
        return dict(_housie_view(conn, r, session_id), won=title)


# ===================================================================== 5c. Lucky Spin (unlocked by spending)

SEGMENTS = [  # (label, prize kind or None, weight). The wheel shows all 8; the server picks with these weights.
    ("Free chai", "chai", 16), ("Try again", None, 22), ("Free juice", "juice", 10), ("So close", None, 18),
    ("Free dessert", "dessert", 7), ("Better luck", None, 17), ("Free starter", "starter", 4), ("Next time", None, 6),
]


def _spin_on():
    if not config.FEATURE_LUCKY_SPIN:
        _off()


def _spin_state(conn, s: dict) -> dict:
    bill = m._bill_paise(conn, s["id"])
    need = config.LUCKY_SPIN_MIN_PAISE
    sp = row(conn.execute("SELECT segment, label FROM lucky_spins WHERE session_id = ?", (s["id"],)).fetchone())
    return {"segments": [x[0] for x in SEGMENTS], "min_paise": need, "bill_paise": bill, "unlocked": bill >= need,
            "more_paise": max(0, need - bill), "spun": bool(sp), "result": sp}


@route("GET", "/api/session/{session_id:int}/spin")
def spin_state(req: Request, session_id: int):
    _spin_on()
    with db() as conn:
        return _spin_state(conn, _playing_session(conn, session_id, req))


@route("POST", "/api/session/{session_id:int}/spin")
def spin(req: Request, session_id: int):
    """One spin per table visit, once the accepted bill reaches LUCKY_SPIN_MIN_RUPEES. The server picks the result."""
    _spin_on()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _playing_session(conn, session_id, req)
        st = _spin_state(conn, s)
        if st["spun"]:
            raise HTTPError(409, "Your table already spun the wheel.")
        if not st["unlocked"]:
            raise HTTPError(409, f"Order ₹{st['more_paise'] // 100:,} more to unlock the Lucky Spin.")
        total = sum(w for _, _, w in SEGMENTS)
        x, seg = rng.uniform(0, total), 0
        for i, (_, _, w) in enumerate(SEGMENTS):
            if x < w:
                seg = i
                break
            x -= w
        label, kind, _ = SEGMENTS[seg]
        conn.execute("INSERT INTO lucky_spins (session_id, segment, label, created_at) VALUES (?, ?, ?, ?)", (session_id, seg, label, now_iso()))
        if kind:
            award_prize(conn, s, "Lucky Spin", kind, label.replace("Free ", ""))
        return dict(_spin_state(conn, s), landed=seg, prize=label if kind else None)
