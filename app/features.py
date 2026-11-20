"""Phase 2 features (each behind a FEATURE_* switch in .env):

1. Kannada voice alerts on the dashboard (announcements + one-dashboard claim)
2. Voice ordering at the table          (Sarvam STT -> intent JSON -> menu matching in code)
3. Menu photo / PDF -> draft menu       (Sarvam Doc AI -> menu JSON -> owner reviews)
4. Budget order                         (pure code: app/budget.py)
5. Voice "call waiter" / "get the bill" (reuses the same helpers as the buttons)
+  Table Quiz: a live quiz between tables; the winning table gets a free tea added at Rs 0.

Rules: the AI never decides money (prices, totals, availability and payment come from the database),
nothing is ordered or saved without a human tapping confirm, and every AI failure has a friendly fallback.
"""
import base64
import difflib
import json
import random
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import ai, config
from . import main as m
from .budget import build_budget_basket, kind_of
from .db import BILL_REQUESTED, OPEN, PAID, PENDING, ACCEPTED, db, now_iso, row, rows
from .quiz_questions import QUESTIONS
from .web import HTTPError, Request

route = m.app.route


def _off():
    raise HTTPError(404, "Not found")


def _rs(paise: int) -> str:
    return f"{paise // 100}" if paise % 100 == 0 else f"{paise / 100:.2f}"


# ===================================================================== 1. Kannada alerts

def announce(conn, restaurant_id: int, table_number: int, event: str, items=None, amount_paise: int | None = None) -> None:
    """Create an announcement from FIXED templates (no AI), so the words are always right."""
    if not config.FEATURE_KANNADA_ALERTS:
        return
    n = table_number
    if event == "start":
        kn, en = f"ಟೇಬಲ್ {n}, ಆರ್ಡರ್ ಮಾಡಲು ಅನುಮತಿ ಕೇಳುತ್ತಿದ್ದಾರೆ.", f"Table {n} wants to order."
    elif event == "order":
        lines = items or []
        kn_items = ", ".join(f"{q} {it.get('name_local') or it['name']}" for q, it in lines[:6])
        en_items = ", ".join(f"{q} {it['name']}" for q, it in lines[:6])
        more = len(lines) > 6
        kn = f"ಟೇಬಲ್ {n}, ಹೊಸ ಆರ್ಡರ್. {kn_items}{' ಮತ್ತು ಇನ್ನಷ್ಟು' if more else ''}."
        en = f"Table {n}, new order: {en_items}{' and more' if more else ''}."
    elif event == "paid":
        kn, en = (f"ಟೇಬಲ್ {n}, ಹಣ ಪಾವತಿಯಾಗಿದೆ. ಒಟ್ಟು {_rs(amount_paise or 0)} ರೂಪಾಯಿ.",
                  f"Table {n} has paid. Total {_rs(amount_paise or 0)} rupees.")
    elif event == "waiter":
        kn, en = f"ಟೇಬಲ್ {n}, ವೇಟರ್ ಬೇಕು.", f"Table {n} needs a waiter."
    elif event == "bill":
        kn, en = f"ಟೇಬಲ್ {n}, ಬಿಲ್ ಕೇಳುತ್ತಿದ್ದಾರೆ.", f"Table {n} wants the bill."
    elif event == "quiz":
        kn, en = f"ಟೇಬಲ್ {n}, ಕ್ವಿಜ್ ಗೆದ್ದಿದ್ದಾರೆ. ಉಚಿತ ಚಹಾ ಕೊಡಿ.", f"Table {n} won the quiz. Give them a free tea."
    elif event == "share_paid":
        kn, en = (f"ಟೇಬಲ್ {n}, ಒಬ್ಬರ ಪಾಲು ಪಾವತಿಯಾಗಿದೆ. {_rs(amount_paise or 0)} ರೂಪಾಯಿ.",
                  f"Table {n}: one share paid, {_rs(amount_paise or 0)} rupees.")
    elif event == "store_order":  # table_number carries the store order number here
        kn, en = (f"ಹೊಸ ಆನ್‌ಲೈನ್ ಆರ್ಡರ್ ಸಂಖ್ಯೆ {n}, ಪಾವತಿಯಾಗಿದೆ. {_rs(amount_paise or 0)} ರೂಪಾಯಿ.",
                  f"New paid order number {n}, {_rs(amount_paise or 0)} rupees.")
    else:
        return
    conn.execute(
        "INSERT INTO announcements (restaurant_id, table_number, event_type, text_kn, text_en, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)", (restaurant_id, n, event, kn, en, now_iso()))


def _ago_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def dashboard_extras(conn, restaurant_id: int) -> dict:
    out = {"announcements": [], "quiz_prizes": []}
    if config.FEATURE_TABLE_QUIZ:
        _quiz_finalize_due(conn, restaurant_id)  # first, so a winner's announcement is in this same response
    if config.FEATURE_KANNADA_ALERTS:
        out["announcements"] = rows(conn.execute(
            "SELECT id, table_number, event_type, text_kn, text_en, claimed, created_at FROM announcements "
            "WHERE restaurant_id = ? AND created_at >= ? ORDER BY id", (restaurant_id, _ago_iso(120))))
    if config.FEATURE_TABLE_QUIZ:
        out["quiz_prizes"] = rows(conn.execute(
            "SELECT q.id AS round_id, q.winner_table AS table_number, q.winner_session_id AS session_id, q.winner_score AS score "
            "FROM quiz_rounds q JOIN table_sessions s ON s.id = q.winner_session_id "
            "WHERE q.restaurant_id = ? AND q.reward_status = 'pending' AND s.status IN (?, ?, ?) ORDER BY q.id",
            (restaurant_id, OPEN, BILL_REQUESTED, PAID)))
    return out


@route("POST", "/api/announcements/{ann_id:int}/claim")
def claim_announcement(req: Request, ann_id: int):
    owner = m.require_owner(req)
    if not config.FEATURE_KANNADA_ALERTS:
        _off()
    with db() as conn:
        a = row(conn.execute("SELECT * FROM announcements WHERE id = ? AND restaurant_id = ?",
                             (ann_id, owner["restaurant_id"])).fetchone())
        if a is None:
            raise HTTPError(404, "Not found")
        won = conn.execute("UPDATE announcements SET claimed = 1 WHERE id = ? AND claimed = 0", (ann_id,)).rowcount == 1
        lang = conn.execute("SELECT language FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()[0]
    out = {"id": ann_id, "audio": None, "text_kn": a["text_kn"], "text_en": a["text_en"]}
    if not won:  # another dashboard already spoke it
        return out
    speak_text, speak_lang = (a["text_kn"], "kn-IN") if lang == "kn-IN" else (a["text_en"], "en-IN")
    try:
        wav = ai.tts(speak_text, speak_lang)
        out["audio"] = "data:audio/wav;base64," + base64.b64encode(wav).decode()
    except ai.AIError:
        pass  # the text still shows on the dashboard
    return out


# ===================================================================== 2/4/5. voice ordering, budget, voice actions

INTENT_PROMPT = """You extract structured data from what a restaurant guest said. They may speak Kannada, Hindi, Tamil, Telugu, English or a mix.
Reply with ONE JSON object only, no other text:
{"intent": "add_items" | "budget_order" | "call_waiter" | "request_bill" | "split_bill" | "unknown",
 "items": [{"name": string, "qty": integer}],
 "budget_rupees": number | null,
 "people": integer | null,
 "meal": "breakfast" | "lunch" | "dinner" | "snacks" | null,
 "split_mode": "equal" | "items" | null,
 "note": string | null}
Rules:
- Use item names from this menu, written exactly as in the menu: {MENU_NAMES}
- If they name something not on the menu, keep their words as the name.
- "two", "do", "eradu", "rendu" etc. are quantities. Default qty is 1.
- Never invent prices. Never add items they didn't ask for.
- "waiter", "help", "someone come" -> call_waiter. "bill", "check", "pay" -> request_bill.
- A budget with a number of people ("800 rupees for 4 people") -> budget_order.
- "split equally among 3", "divide the bill by 4" -> split_bill, split_mode "equal", people = that number.
- "I'll pay for my items", "separate bills" -> split_bill, split_mode "items"."""

LANG_NAMES = {"kn-IN": "Kannada", "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "ml-IN": "Malayalam",
              "mr-IN": "Marathi", "bn-IN": "Bengali", "gu-IN": "Gujarati", "pa-IN": "Punjabi", "od-IN": "Odia",
              "en-IN": "English"}


def _guess_lang(text: str) -> str:
    for lo, hi, code in ((0x0C80, 0x0CFF, "kn-IN"), (0x0900, 0x097F, "hi-IN"), (0x0B80, 0x0BFF, "ta-IN"),
                         (0x0C00, 0x0C7F, "te-IN"), (0x0D00, 0x0D7F, "ml-IN"), (0x0980, 0x09FF, "bn-IN"),
                         (0x0A80, 0x0AFF, "gu-IN"), (0x0A00, 0x0A7F, "pa-IN")):
        if any(lo <= ord(ch) <= hi for ch in text):
            return code
    return "en-IN"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_ALIAS_SUBS = [(r"\bdose\b", "dosa"), (r"\bdosai\b", "dosa"), (r"\bkaapi\b|\bkapi\b|\bkafi\b", "coffee"),
               (r"\btea\b", "chai"), (r"\bidly\b", "idli"), (r"\bvade\b|\bwada\b", "vada"), (r"\bbaath\b", "bath"),
               (r"\bmeal\b", "meals"), (r"\bjamoon\b|\bjamun\b", "jamun"), (r"s\b", "")]


def _alias(s: str) -> str:
    s = _norm(s)
    for pat, rep in _ALIAS_SUBS:
        s = re.sub(pat, rep, s)
    return s.strip()


def match_items(raw_items: list, menu: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Map spoken names to menu items in CODE. Returns (lines, not_found, unavailable)."""
    exact, alias = {}, {}
    for it in menu:
        for label in (it["name"], it.get("name_local") or ""):
            if label:
                exact.setdefault(_norm(label), it)
                alias.setdefault(_alias(label), it)
    alias_keys = list(alias)
    merged: dict[int, int] = {}
    order: list[int] = []
    not_found, unavailable = [], []
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            continue
        said = str(raw.get("name") or "").strip()
        if not said:
            continue
        try:
            qty = int(float(raw.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, min(50, qty))
        it = exact.get(_norm(said)) or alias.get(_alias(said))
        if it is None:  # "kaapi" -> "coffee": use it if exactly ONE dish name contains those words
            words = set(_alias(said).split())
            owners = {alias[k]["id"]: alias[k] for k in alias_keys if words and words <= set(k.split())}
            it = next(iter(owners.values())) if len(owners) == 1 else None
        if it is None:
            close = difflib.get_close_matches(_alias(said), alias_keys, n=1, cutoff=0.75)
            it = alias[close[0]] if close else None
        if it is None:
            not_found.append(said)
            continue
        if not it.get("available", 1):
            unavailable.append(it["name"])
            continue
        if it["id"] not in merged:
            order.append(it["id"])
        merged[it["id"]] = min(50, merged.get(it["id"], 0) + qty)
    by_id = {it["id"]: it for it in menu}
    lines = [{"menu_item_id": i, "name": by_id[i]["name"], "name_local": by_id[i].get("name_local", ""),
              "qty": merged[i], "unit_price_paise": by_id[i]["price_paise"],
              "line_total_paise": by_id[i]["price_paise"] * merged[i]} for i in order]
    return lines, sorted(set(not_found)), sorted(set(unavailable))


def find_menu_item(said: str, menu: list[dict]):
    """One dish by name (available or not), using the same matching as voice ordering."""
    if not said.strip():
        return None
    by_id = {it["id"]: it for it in menu}
    probe = [dict(it, available=1) for it in menu]  # match even finished dishes
    lines, _, _ = match_items([{"name": said, "qty": 1}], probe)
    return by_id.get(lines[0]["menu_item_id"]) if lines else None


def _localise(text_en: str, lang: str) -> tuple[str, str | None]:
    """English reply -> guest's language (+ audio). Falls back to English text and no audio."""
    text, out_lang = text_en, "en-IN"
    if lang and lang != "en-IN" and lang in LANG_NAMES:
        try:
            t = ai.chat([{"role": "system", "content": f"Translate the user's text into {LANG_NAMES[lang]}. Keep all numbers "
                                                       "and the ₹ sign as digits exactly as they are. Reply with the translation only."},
                         {"role": "user", "content": text_en}]).strip().strip('"')
            if t:
                text, out_lang = t, lang
        except ai.AIError:
            pass
    audio = None
    try:
        audio = "data:audio/wav;base64," + base64.b64encode(ai.tts(text, out_lang)).decode()
    except ai.AIError:
        pass
    return text, audio


def _items_sentence(lines: list[dict]) -> str:
    parts = [f"{l['qty']} {l['name']}" for l in lines]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _menu_for(conn, restaurant_id: int) -> list[dict]:
    return m._menu(conn, restaurant_id)  # all dishes, including unavailable ones (so we can say so)


def _proposal(intent: str, lines: list[dict], **extra) -> dict:
    base = {"intent": intent, "proposed_items": lines, "total_paise": sum(l["line_total_paise"] for l in lines),
            "not_found": [], "unavailable": [], "suggestion": None, "budget_paise": None, "remaining_paise": None,
            "min_budget_paise": None, "action": None, "ok": True}
    base.update(extra)
    return base


@route("POST", "/api/session/{session_id:int}/voice")
def voice(req: Request, session_id: int):
    f = config.features()
    if not f["voice_order"]:
        _off()
    fields, files = req.form()
    audio = files.get("audio")
    text = (fields.get("text") or "").strip()[:300]
    language = (fields.get("language") or "").strip() or None
    with db() as conn:
        s = m._guest_session(conn, session_id, req)
        if s["status"] not in (OPEN, BILL_REQUESTED):
            raise HTTPError(409, "Your table isn't open for ordering right now.")
        menu = _menu_for(conn, s["restaurant_id"])
    if audio is not None and audio.data:
        if len(audio.data) > 6_000_000:
            raise HTTPError(400, "That recording is too long. Keep it under 20 seconds.")
        try:
            heard = ai.stt(audio.data, audio.filename or "voice.wav", audio.content_type or "audio/wav", language)
        except ai.AIError:
            return _friendly("I couldn't hear that clearly. Please try again, or tap to order.")
        transcript, lang = heard["transcript"], heard.get("language_code") or language or "en-IN"
    elif text:
        transcript, lang = text, language or _guess_lang(text)
    else:
        raise HTTPError(400, "Say or type what you'd like.")
    if not transcript:
        return _friendly("I didn't catch anything. Please try again, or tap to order.")

    names = [it["name"] for it in menu if it.get("available", 1)]
    try:
        data = ai.chat_json([{"role": "system", "content": INTENT_PROMPT.replace("{MENU_NAMES}", "; ".join(names))},
                             {"role": "user", "content": transcript}])
    except ai.AIError:
        return _friendly("Sorry, I couldn't understand that right now. Please tap to order.", transcript, lang)
    if not isinstance(data, dict):
        data = {}
    intent = str(data.get("intent") or "unknown")

    if intent == "budget_order" and f["budget_order"]:
        try:
            budget = int(round(float(data.get("budget_rupees") or 0) * 100))
            people = int(data.get("people") or 1)
        except (TypeError, ValueError):
            budget, people = 0, 1
        res = build_budget_basket(menu, budget, max(1, min(20, people)), data.get("meal"))
        out = _proposal("budget_order", res["proposed_items"], ok=res["ok"], budget_paise=res["budget_paise"],
                        remaining_paise=res["remaining_paise"], suggestion=res["suggestion"],
                        min_budget_paise=res["min_budget_paise"])
        reply_en = res["reply_text"] + (" Add to your order?" if res["ok"] else "")
        if s["status"] != OPEN:
            out["ok"], reply_en = False, "Your bill is already requested, so new orders can't be added."
    elif intent == "split_bill" and f.get("split_bill") and f["voice_actions"]:
        out = _proposal("split_bill", [])
        mode = "items" if data.get("split_mode") == "items" else "equal"
        try:
            people = int(data.get("people") or 0)
        except (TypeError, ValueError):
            people = 0
        from . import upgrades
        try:
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                s2 = m._guest_session(conn, session_id, req)
                if s2["status"] == OPEN:
                    m._request_bill(conn, s2)  # same rules as the Request bill button
                me = conn.execute("SELECT id FROM session_guests WHERE token = ?", (req.header("X-Guest-Token"),)).fetchone()
                upgrades.make_split(conn, s2, mode, people if mode == "equal" else None, [], me["id"] if me else None)
                bill = m._bill_paise(conn, session_id)
            reply_en = (f"Done. The bill of ₹{_rs(bill)} is split {'equally between ' + str(people) + ' people' if mode == 'equal' else 'by what each phone ordered'}. "
                        "Each person can pay their share from the Bill tab.")
            out["action"] = {"type": "split", "ok": True}
            out["total_paise"] = bill
        except HTTPError as e:
            out["ok"], out["action"] = False, {"type": "split", "ok": False}
            reply_en = e.detail if not (mode == "equal" and not 2 <= people <= 20) else "How many people should share the bill? Say a number from 2 to 20."
    elif intent in ("call_waiter", "request_bill") and f["voice_actions"]:
        out = _proposal(intent, [])
        try:
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                s2 = m._guest_session(conn, session_id, req)
                if intent == "call_waiter":
                    new = m._call_waiter(conn, s2, "Asked by voice")
                    reply_en = (f"I've called the waiter for table {s2['table_number']}." if new
                                else "A waiter is already on the way.")
                    out["action"] = {"type": "waiter", "ok": True}
                else:
                    already = s2["status"] == BILL_REQUESTED
                    m._request_bill(conn, s2)
                    bill = m._bill_paise(conn, session_id)
                    reply_en = (f"Your bill is already requested: ₹{_rs(bill)}. Tap Pay when ready." if already
                                else f"Here's your bill: ₹{_rs(bill)}. Tap Pay when ready.")
                    out["action"] = {"type": "bill", "ok": True}
                    out["total_paise"] = bill
        except HTTPError as e:
            out["ok"], out["action"] = False, {"type": "waiter" if intent == "call_waiter" else "bill", "ok": False}
            reply_en = e.detail
    elif intent == "add_items" or (intent == "budget_order" and not f["budget_order"]):
        lines, not_found, unavailable = match_items(data.get("items") or [], menu)
        out = _proposal("add_items", lines, not_found=not_found, unavailable=unavailable, ok=bool(lines))
        if s["status"] != OPEN:
            out["ok"], reply_en = False, "Your bill is already requested, so new orders can't be added."
        elif lines:
            reply_en = f"{_items_sentence(lines)}, ₹{_rs(out['total_paise'])}. Add to your order?"
        else:
            reply_en = "I couldn't find those dishes on the menu. Please try again or tap to order."
        if lines and not_found:
            reply_en += f" I couldn't find: {', '.join(not_found)}."
        if unavailable:
            reply_en += f" Not available today: {', '.join(unavailable)}."
    else:
        out = _proposal("unknown", [], ok=False)
        reply_en = "Sorry, I didn't understand. You can say dishes like '2 masala dosa and 1 filter coffee'."

    reply_text, reply_audio = _localise(reply_en, lang)
    out.update(transcript=transcript, language=lang, reply_text=reply_text, reply_text_en=reply_en, reply_audio=reply_audio)
    return out


def _friendly(msg: str, transcript: str = "", lang: str = "en-IN") -> dict:
    out = _proposal("unknown", [], ok=False)
    out.update(transcript=transcript, language=lang, reply_text=msg, reply_text_en=msg, reply_audio=None, error=True)
    return out


@route("POST", "/api/session/{session_id:int}/budget")
def budget(req: Request, session_id: int):
    if not config.features()["budget_order"]:
        _off()
    d = req.json()
    try:
        rupees = float(d.get("budget_rupees"))
        people = int(d.get("people"))
    except (TypeError, ValueError):
        raise HTTPError(400, "Enter a budget and the number of people.")
    if not (1 <= rupees <= 100000) or not (1 <= people <= 20):
        raise HTTPError(400, "Budget must be ₹1 to ₹1,00,000 and people 1 to 20.")
    meal = d.get("meal") if d.get("meal") in ("breakfast", "lunch", "dinner", "snacks") else None
    with db() as conn:
        s = m._guest_session(conn, session_id, req)
        if s["status"] != OPEN:
            raise HTTPError(409, "Ordering is closed for this table.")
        menu = _menu_for(conn, s["restaurant_id"])
    res = build_budget_basket(menu, int(round(rupees * 100)), people, meal)
    out = _proposal("budget_order", res["proposed_items"], ok=res["ok"], budget_paise=res["budget_paise"],
                    remaining_paise=res["remaining_paise"], suggestion=res["suggestion"],
                    min_budget_paise=res["min_budget_paise"])
    out.update(reply_text=res["reply_text"], reply_text_en=res["reply_text"], reply_audio=None, transcript="", language="en-IN")
    return out


# ===================================================================== 3. menu photo / PDF -> draft menu

MENU_PROMPT = """You convert a restaurant menu (given as text extracted from a photo) into JSON.
Reply with ONE JSON object only:
{"items": [{"name": string, "name_local": string | null, "category": "main" | "starter" | "breakfast" | "drink" | "dessert" | "snack" | "other", "price_rupees": number | null}]}
Rules:
- One entry per item and size. "Coffee small 20 / large 30" -> two items: "Coffee (small)" 20 and "Coffee (large)" 30.
- name = English name; name_local = the name in the original script if the menu has one.
- price_rupees = the number printed next to the item. If no price is clearly printed, use null. Never guess a price.
- Ignore headings, addresses, phone numbers, taxes and notes; they are not items.
- Do not invent items that are not in the text."""

CATEGORY_LABELS = {"main": "Main Course", "starter": "Starters", "breakfast": "Breakfast", "drink": "Beverages",
                   "dessert": "Desserts", "snack": "Snacks", "other": "Other"}
ALLOWED_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}


def menu_photo(req: Request):
    if not config.features()["menu_photo"]:
        _off()
    fields, files = req.form()
    f = files.get("file")
    if f is None or not f.data:
        raise HTTPError(400, "Choose a photo or PDF of the menu")
    if len(f.data) > 10_000_000:
        raise HTTPError(400, "File is too big (max 10 MB)")
    ext = (f.filename or "").rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
    ctype = ALLOWED_TYPES.get(ext) or (f.content_type if f.content_type in ALLOWED_TYPES.values() else None)
    if not ctype:
        raise HTTPError(400, "Please upload a JPG, PNG or PDF")
    language = fields.get("language") or "en-IN"
    if language not in LANG_NAMES:
        language = "en-IN"
    try:
        markdown = ai.read_document(f.data, f.filename or f"menu.{ext or 'jpg'}", ctype, language)
        data = ai.chat_json([{"role": "system", "content": MENU_PROMPT}, {"role": "user", "content": markdown[:20000]}])
    except ai.AIError:
        raise HTTPError(502, "Couldn't read the photo. Please add items manually.")
    raw = data.get("items") if isinstance(data, dict) else data if isinstance(data, list) else []
    drafts, warnings, seen = [], [], set()
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:80]
        if not name:
            continue
        price = it.get("price_rupees")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        if price is not None and not (0 < price <= 100000):
            price = None
        price_paise = int(round(price * 100)) if price is not None else None
        key = (name.lower(), price_paise)
        if key in seen:
            continue
        seen.add(key)
        cat = str(it.get("category") or "other").lower()
        cat = cat if cat in CATEGORY_LABELS else "other"
        drafts.append({"name": name, "name_local": str(it.get("name_local") or "").strip()[:80],
                       "category": CATEGORY_LABELS[cat], "price_paise": price_paise, "include": True})
    missing = sum(1 for d in drafts if d["price_paise"] is None)
    if missing:
        warnings.append(f"{missing} dish{'es' if missing > 1 else ''} had no clear price. Please fill them in.")
    if not drafts:
        raise HTTPError(422, "Couldn't find any dishes in that file. Please add items manually.")
    return {"draft_items": drafts, "items": drafts, "raw_markdown": markdown[:20000], "warnings": warnings,
            "categories": list(CATEGORY_LABELS.values())}


# ===================================================================== Table Quiz (live, between tables)

LOBBY_SECONDS, QUESTION_SECONDS, REVEAL_SECONDS, QUESTIONS_PER_ROUND = 30, 15, 4, 8
SLOT = QUESTION_SECONDS + REVEAL_SECONDS
ROUND_SECONDS = QUESTIONS_PER_ROUND * SLOT
MIN_TABLES_FOR_PRIZE = 2


def _quiz_current(conn, restaurant_id: int):
    """Latest round that is still running, or finished in the last 3 minutes."""
    r = row(conn.execute("SELECT * FROM quiz_rounds WHERE restaurant_id = ? ORDER BY id DESC LIMIT 1",
                         (restaurant_id,)).fetchone())
    if r and time.time() < r["starts_at"] + ROUND_SECONDS + 180:
        return r
    return None


def _quiz_scores(conn, round_id: int) -> list[dict]:
    return rows(conn.execute(
        "SELECT p.session_id, p.table_number, COALESCE(SUM(a.points), 0) AS score, COUNT(a.q_index) AS answered, "
        "COALESCE(SUM(a.correct), 0) AS correct, COALESCE(MAX(a.answered_at), p.joined_at) AS last_at "
        "FROM quiz_players p LEFT JOIN quiz_answers a ON a.round_id = p.round_id AND a.session_id = p.session_id "
        "WHERE p.round_id = ? GROUP BY p.session_id ORDER BY score DESC, last_at ASC", (round_id,)))


def _quiz_finalize_due(conn, restaurant_id: int) -> None:
    for r in rows(conn.execute("SELECT * FROM quiz_rounds WHERE restaurant_id = ? AND finalized = 0 AND starts_at + ? <= ?",
                               (restaurant_id, ROUND_SECONDS, time.time()))):
        scores = _quiz_scores(conn, r["id"])
        if not conn.execute("UPDATE quiz_rounds SET finalized = 1 WHERE id = ? AND finalized = 0", (r["id"],)).rowcount:
            continue  # someone else finalized it
        if scores and scores[0]["score"] > 0:
            w = scores[0]
            eligible = len(scores) >= MIN_TABLES_FOR_PRIZE
            conn.execute("UPDATE quiz_rounds SET winner_session_id = ?, winner_table = ?, winner_score = ?, reward_status = ? "
                         "WHERE id = ?", (w["session_id"], w["table_number"], w["score"],
                                          "pending" if eligible else "none", r["id"]))
            if eligible:
                announce(conn, restaurant_id, w["table_number"], "quiz")


def _quiz_state(conn, restaurant_id: int, session_id: int | None) -> dict:
    _quiz_finalize_due(conn, restaurant_id)
    r = _quiz_current(conn, restaurant_id)
    now = time.time()
    if not r:
        return {"phase": "none", "now": now, "min_tables": MIN_TABLES_FOR_PRIZE}
    qs = json.loads(r["questions"])
    t = now - r["starts_at"]
    scores = _quiz_scores(conn, r["id"])
    joined = any(sc["session_id"] == session_id for sc in scores) if session_id else False
    st = {"round_id": r["id"], "now": now, "q_total": len(qs), "min_tables": MIN_TABLES_FOR_PRIZE, "joined": joined,
          "players": [{"table": sc["table_number"], "score": sc["score"], "correct": sc["correct"],
                       "me": sc["session_id"] == session_id} for sc in scores]}
    if t < 0:
        st.update(phase="lobby", starts_in=round(-t, 1))
        return st
    if t >= ROUND_SECONDS:
        st.update(phase="done", winner=None, reward_status=r["reward_status"])
        if r["winner_table"] is not None:
            st["winner"] = {"table": r["winner_table"], "score": r["winner_score"], "me": r["winner_session_id"] == session_id}
        return st
    qi, into = int(t // SLOT), t % SLOT
    q = qs[qi]
    st.update(q_index=qi, question={"text": q["q"], "options": q["options"]})
    mine = None
    if session_id:
        a = conn.execute("SELECT choice, correct, points FROM quiz_answers WHERE round_id = ? AND session_id = ? AND q_index = ?",
                         (r["id"], session_id, qi)).fetchone()
        mine = dict(a) if a else None
    if into < QUESTION_SECONDS:
        st.update(phase="question", time_left=round(QUESTION_SECONDS - into, 1),
                  my_answer={"choice": mine["choice"]} if mine else None)
    else:
        st.update(phase="reveal", time_left=round(SLOT - into, 1), correct=q["answer"], my_answer=mine)
    return st


def _quiz_session(conn, session_id: int, req: Request) -> dict:
    if not config.FEATURE_TABLE_QUIZ:
        _off()
    s = m._guest_session(conn, session_id, req)
    if s["status"] not in (OPEN, BILL_REQUESTED, PAID):
        raise HTTPError(409, "The quiz is for tables that are ordering. Start ordering first.")
    return s


@route("GET", "/api/t/{token}/quiz")
def quiz_state(req: Request, token: str):
    if not config.FEATURE_TABLE_QUIZ:
        _off()
    sid = None
    with db() as conn:
        t = m._table_by_token(conn, token)
        try:
            sid_q = int(req.query.get("session") or 0)
        except ValueError:
            sid_q = 0
        if sid_q and req.header("X-Guest-Token"):
            try:
                sid = m._guest_session(conn, sid_q, req)["id"]
            except HTTPError:
                sid = None
        return _quiz_state(conn, t["restaurant_id"], sid)


@route("POST", "/api/session/{session_id:int}/quiz/join")
def quiz_join(req: Request, session_id: int):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _quiz_session(conn, session_id, req)
        rid = s["restaurant_id"]
        _quiz_finalize_due(conn, rid)
        r = row(conn.execute("SELECT * FROM quiz_rounds WHERE restaurant_id = ? AND finalized = 0 ORDER BY id DESC LIMIT 1",
                             (rid,)).fetchone())
        now = time.time()
        if r is None:  # nobody is playing: open a lobby so other tables can join
            picks = random.sample(QUESTIONS, QUESTIONS_PER_ROUND)
            qs = []
            for text, opts in picks:
                order = list(range(len(opts)))
                random.shuffle(order)
                qs.append({"q": text, "options": [opts[i] for i in order], "answer": order.index(0)})
            rid_new = conn.execute("INSERT INTO quiz_rounds (restaurant_id, starts_at, questions, created_at) VALUES (?, ?, ?, ?)",
                                   (rid, now + LOBBY_SECONDS, json.dumps(qs, ensure_ascii=False), now_iso())).lastrowid
            r = row(conn.execute("SELECT * FROM quiz_rounds WHERE id = ?", (rid_new,)).fetchone())
        conn.execute("INSERT OR IGNORE INTO quiz_players (round_id, session_id, table_number, joined_at) VALUES (?, ?, ?, ?)",
                     (r["id"], session_id, s["table_number"], now))
        return _quiz_state(conn, rid, session_id)


@route("POST", "/api/session/{session_id:int}/quiz/answer")
def quiz_answer(req: Request, session_id: int):
    d = req.json()
    try:
        round_id, qi, choice = int(d.get("round_id")), int(d.get("q_index")), int(d.get("choice"))
    except (TypeError, ValueError):
        raise HTTPError(400, "Bad answer")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        s = _quiz_session(conn, session_id, req)
        r = row(conn.execute("SELECT * FROM quiz_rounds WHERE id = ? AND restaurant_id = ?",
                             (round_id, s["restaurant_id"])).fetchone())
        if r is None:
            raise HTTPError(404, "Quiz not found")
        if not conn.execute("SELECT 1 FROM quiz_players WHERE round_id = ? AND session_id = ?", (round_id, session_id)).fetchone():
            raise HTTPError(409, "Join the quiz first.")
        now = time.time()
        t = now - r["starts_at"]
        qs = json.loads(r["questions"])
        if t < 0 or int(t // SLOT) != qi or t % SLOT >= QUESTION_SECONDS or qi >= len(qs):
            raise HTTPError(409, "Time's up for that question.")
        if not 0 <= choice < len(qs[qi]["options"]):
            raise HTTPError(400, "Bad answer")
        correct = choice == qs[qi]["answer"]
        time_left = QUESTION_SECONDS - (t % SLOT)
        points = 100 + int(round(100 * time_left / QUESTION_SECONDS)) if correct else 0
        cur = conn.execute("INSERT OR IGNORE INTO quiz_answers (round_id, session_id, q_index, choice, correct, points, answered_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?)", (round_id, session_id, qi, choice, int(correct), points, now))
        if not cur.rowcount:
            raise HTTPError(409, "Your table already answered this one.")
    return {"ok": True, "locked": choice}


@route("POST", "/api/quiz/{round_id:int}/reward")
def quiz_reward(req: Request, round_id: int):
    owner = m.require_owner(req)
    if not config.FEATURE_TABLE_QUIZ:
        _off()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        r = row(conn.execute("SELECT * FROM quiz_rounds WHERE id = ? AND restaurant_id = ?",
                             (round_id, owner["restaurant_id"])).fetchone())
        if r is None or r["reward_status"] != "pending":
            raise HTTPError(409, "This prize was already handled.")
        s = row(conn.execute("SELECT status FROM table_sessions WHERE id = ?", (r["winner_session_id"],)).fetchone())
        if not s or s["status"] not in (OPEN, BILL_REQUESTED, PAID):
            conn.execute("UPDATE quiz_rounds SET reward_status = 'void' WHERE id = ?", (round_id,))
            return {"ok": True, "added": False, "message": "That table has left. Prize cancelled."}
        menu = m._menu(conn, owner["restaurant_id"])
        tea = (next((x for x in menu if re.search(r"masala chai|\bchai\b|\btea\b", x["name"], re.I)), None)
               or next((x for x in menu if re.search(r"coffee|kaapi", x["name"], re.I)), None)
               or min((x for x in menu if kind_of(x["category"], x["name"]) == "drink"),
                      key=lambda x: x["price_paise"], default=None))
        added = False
        if tea:
            ts = now_iso()
            oid = conn.execute("INSERT INTO orders (session_id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                               (r["winner_session_id"], ACCEPTED, ts, ts)).lastrowid
            conn.execute("INSERT INTO order_items (order_id, menu_item_id, name, qty, unit_price_paise) VALUES (?, ?, ?, 1, 0)",
                         (oid, tea["id"], f"{tea['name']} (quiz prize, free)"))
            added = True
        conn.execute("UPDATE quiz_rounds SET reward_status = 'given' WHERE id = ?", (round_id,))
    return {"ok": True, "added": added,
            "message": f"Free {tea['name']} added to table {r['winner_table']} at ₹0." if added
            else f"No tea on the menu: please serve table {r['winner_table']} a free drink by hand."}
