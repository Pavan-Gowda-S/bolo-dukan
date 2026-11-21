"""Part B: Supermarket mode (FEATURE_SUPERMARKET) and the AI Meal Planner (FEATURE_MEAL_PLANNER).

Rules: prices, totals, pack choices, nutrition and payment status come from the database and app/planner.py.
The AI only understands requests, extracts JSON, translates and speaks. Nothing is ordered without a tap.
"""
import base64
import csv
import io
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import qrcode
import qrcode.image.svg

from . import ai, cashfree, config, features, planner
from . import main as m
from .db import db, now_iso, row, rows
from .summary import summarize
from .web import HTTPError, Request, Response, file_response

route = m.app.route
DATA = Path(__file__).resolve().parent / "data"
UNITS = ("g", "ml", "pcs")


def _off():
    raise HTTPError(404, "Not found")


def _json(name: str, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


_cache: dict = {}


def data():
    """Seed data, loaded once: ingredients, recipes, demo products, photos."""
    if not _cache:
        _cache["ingredients"] = {i["id"]: i for i in _json("ingredients.json", [])}
        _cache["recipes"] = _json("recipes.json", [])
        _cache["recipe_by_id"] = {r["id"]: r for r in _cache["recipes"]}
        _cache["demo_products"] = _json("products_demo.json", [])
        _cache["photos"] = _json("photos.json", {})
    return _cache


def photo(key: str):
    """A real photo for a recipe or ingredient. Prefers the local copy (static/img/photos) over hot-linking Wikimedia."""
    if not config.FEATURE_PHOTOS:
        return None
    ph = data()["photos"].get(key)
    if ph and ph.get("local") and (config.STATIC_DIR / ph["local"].removeprefix("/static/")).exists():
        return dict(ph, thumb=ph["local"])
    return ph


def _rs(paise: int) -> str:
    return f"₹{paise // 100:,}" if paise % 100 == 0 else f"₹{paise / 100:,.2f}"


# ===================================================================== hooks used by main.py

def apply_business_type(conn, restaurant_id: int, business_type) -> None:
    if config.FEATURE_SUPERMARKET and business_type == "supermarket":
        conn.execute("UPDATE restaurants SET business_type = 'supermarket' WHERE id = ?", (restaurant_id,))


def next_page(conn, owner_id: int, default: str) -> str:
    if not config.FEATURE_SUPERMARKET:
        return default
    r = conn.execute("SELECT r.business_type FROM owners o JOIN restaurants r ON r.id = o.restaurant_id WHERE o.id = ?",
                     (owner_id,)).fetchone()
    return "/store" if r and r["business_type"] == "supermarket" else default


def _menu_recipe(name: str):
    """Match a restaurant menu dish to a recipe (for nutrition and photos)."""
    rs = data()["recipes"]
    key = features._alias(name)
    for r in rs:
        if features._alias(r["name"]) == key:
            return r
    words = set(key.split())
    best = [r for r in rs if words and set(features._alias(r["name"]).split()) <= words]
    if best:  # e.g. "Benne Masala Dosa" -> "Masala Dosa"
        return max(best, key=lambda r: len(features._alias(r["name"])))
    import difflib
    names = {features._alias(r["name"]): r for r in rs}
    close = difflib.get_close_matches(key, list(names), n=1, cutoff=0.8)
    return names[close[0]] if close else None


def menu_extras(menu: list[dict]) -> None:
    """Add approx. nutrition and a real photo to restaurant menu dishes (in place)."""
    if not (config.FEATURE_NUTRITION or config.FEATURE_PHOTOS):
        return
    for item in menu:
        r = _menu_recipe(item["name"])
        if not r:
            continue
        if config.FEATURE_NUTRITION:
            item["nutrition"] = planner.recipe_nutrition(r, data()["ingredients"])
            item["nutrition_recipe"] = r["name"]
        ph = photo(f"recipe:{r['id']}")
        if ph and not item.get("photo_url"):
            item["photo_url"], item["photo_credit"] = ph["thumb"], f"{ph['author']} · {ph['license']} · Wikimedia Commons"


# ===================================================================== owner: store dashboard

def _require_store(req: Request) -> dict:
    owner = m.require_owner(req)
    if not config.FEATURE_SUPERMARKET:
        _off()
    with db() as conn:
        r = conn.execute("SELECT business_type FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()
    if r["business_type"] != "supermarket":
        raise HTTPError(409, "This account is a restaurant, not a supermarket.")
    return owner


def _products(conn, store_id: int, only_available: bool = False) -> list[dict]:
    q = "SELECT * FROM products WHERE store_id = ? AND deleted = 0"
    if only_available:
        q += " AND available = 1 AND stock > 0"
    return rows(conn.execute(q + " ORDER BY category, name", (store_id,)))


def _product_in(d: dict) -> dict:
    name = str(d.get("name") or "").strip()[:100]
    if not name:
        raise HTTPError(400, "Enter a product name")
    unit = str(d.get("pack_unit") or "").strip().lower()
    if unit not in UNITS:
        raise HTTPError(400, "Pack unit must be g, ml or pcs")
    try:
        size = float(d.get("pack_size"))
        price = int(d.get("price_paise"))
        stock = int(d.get("stock", 100))
    except (TypeError, ValueError):
        raise HTTPError(400, "Pack size, price and stock must be numbers")
    if not (0 < size <= 100000) or not (100 <= price <= 10_000_000) or not (0 <= stock <= 100000):
        raise HTTPError(400, "Check the pack size, price (₹1 or more) and stock")
    ing = d.get("ingredient_id") or None
    if ing and ing not in data()["ingredients"]:
        ing = None
    diet = d.get("diet") if d.get("diet") in ("veg", "vegan", "egg", "nonveg") else "veg"
    return {"name": name, "brand": str(d.get("brand") or "")[:60], "category": str(d.get("category") or "Other")[:60] or "Other",
            "pack_size": size, "pack_unit": unit, "price_paise": price, "stock": stock,
            "available": 0 if d.get("available") in (False, 0, "0") else 1, "ingredient_id": ing,
            "image_url": str(d.get("image_url") or "")[:500], "topup": 1 if d.get("topup") else 0, "diet": diet}


def _insert_product(conn, store_id: int, p: dict) -> int:
    return conn.execute(
        "INSERT INTO products (store_id, name, brand, category, pack_size, pack_unit, price_paise, stock, available, "
        "ingredient_id, image_url, topup, diet) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (store_id, p["name"], p["brand"], p["category"], p["pack_size"], p["pack_unit"], p["price_paise"], p["stock"],
         p["available"], p["ingredient_id"], p["image_url"], p["topup"], p["diet"])).lastrowid


def _with_photo(p: dict) -> dict:
    p = dict(p)
    if not p.get("image_url") and p.get("ingredient_id"):
        ph = photo(f"ingredient:{p['ingredient_id']}")
        if ph:
            p["image_url"], p["image_credit"] = ph["thumb"], f"{ph['author']} · {ph['license']}"
    return p


@route("GET", "/api/store/products")
def store_products(req: Request):
    owner = _require_store(req)
    with db() as conn:
        return {"products": [_with_photo(p) for p in _products(conn, owner["restaurant_id"])],
                "ingredients": [{"id": i["id"], "name": i["name"], "unit": i["unit"]} for i in data()["ingredients"].values()]}


@route("POST", "/api/store/products")
def store_product_add(req: Request):
    owner = _require_store(req)
    p = _product_in(req.json())
    with db() as conn:
        return {"ok": True, "id": _insert_product(conn, owner["restaurant_id"], p)}


@route("PUT", "/api/store/products/{pid:int}")
def store_product_edit(req: Request, pid: int):
    owner = _require_store(req)
    p = _product_in(req.json())
    with db() as conn:
        cur = conn.execute(
            "UPDATE products SET name=?, brand=?, category=?, pack_size=?, pack_unit=?, price_paise=?, stock=?, available=?, "
            "ingredient_id=?, image_url=?, topup=?, diet=? WHERE id = ? AND store_id = ? AND deleted = 0",
            (p["name"], p["brand"], p["category"], p["pack_size"], p["pack_unit"], p["price_paise"], p["stock"], p["available"],
             p["ingredient_id"], p["image_url"], p["topup"], p["diet"], pid, owner["restaurant_id"]))
        if not cur.rowcount:
            raise HTTPError(404, "Product not found")
    return {"ok": True}


@route("DELETE", "/api/store/products/{pid:int}")
def store_product_delete(req: Request, pid: int):
    owner = _require_store(req)
    with db() as conn:
        conn.execute("UPDATE products SET deleted = 1 WHERE id = ? AND store_id = ?", (pid, owner["restaurant_id"]))
    return {"ok": True}


@route("POST", "/api/store/products/bulk")
def store_products_bulk(req: Request):
    owner = _require_store(req)
    items = req.json().get("items")
    if not isinstance(items, list) or not items or len(items) > 500:
        raise HTTPError(400, "Nothing to save")
    clean = [_product_in(x if isinstance(x, dict) else {}) for x in items]
    with db() as conn:
        for p in clean:
            _insert_product(conn, owner["restaurant_id"], p)
    return {"ok": True, "added": len(clean)}


@route("POST", "/api/store/products/csv")
def store_products_csv(req: Request):
    owner = _require_store(req)
    _, files = req.form()
    f = files.get("file")
    if f is None or len(f.data) > 2_000_000:
        raise HTTPError(400, "Choose a CSV file (max 2 MB)")
    try:
        text = f.data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = f.data.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
    need = {"name", "pack_size", "pack_unit", "price"}
    if not need <= set(fields):
        raise HTTPError(400, "CSV columns: name, brand, category, pack_size, pack_unit (g/ml/pcs), price, stock, ingredient_id")
    added = skipped = 0
    with db() as conn:
        for rec in reader:
            g = lambda k: (rec.get(fields[k]) if k in fields else "") or ""
            try:
                price = int(round(float(re.sub(r"[^\d.]", "", g("price")) or 0) * 100))
                p = _product_in({"name": g("name"), "brand": g("brand"), "category": g("category"), "pack_size": g("pack_size"),
                                 "pack_unit": g("pack_unit").lower(), "price_paise": price, "stock": g("stock") or 100,
                                 "ingredient_id": g("ingredient_id") or None})
            except HTTPError:
                skipped += 1
                continue
            _insert_product(conn, owner["restaurant_id"], p)
            added += 1
    return {"ok": True, "added": added, "skipped": skipped}


PRODUCT_PROMPT = """You convert a shop's price list (text extracted from a photo) into JSON.
Reply with ONE JSON object only:
{"items": [{"name": string, "brand": string | null, "category": string | null, "pack_size": number | null, "pack_unit": "g" | "ml" | "pcs" | null, "price_rupees": number | null}]}
Rules:
- One entry per product and pack size. "Toor dal 500g 82 / 1kg 158" -> two items.
- Convert kg to g and litres to ml. Count items like eggs in pcs.
- price_rupees = the number printed for that pack. If no price is clearly printed, use null. Never guess.
- Ignore headings, addresses, phone numbers, offers and taxes. Do not invent products."""


@route("POST", "/api/store/products/photo")
def store_products_photo(req: Request):
    owner = _require_store(req)
    if not config.features()["menu_photo"]:
        _off()
    fields, files = req.form()
    f = files.get("file")
    if f is None or not f.data or len(f.data) > 10_000_000:
        raise HTTPError(400, "Choose a JPG, PNG or PDF (max 10 MB)")
    ext = (f.filename or "").rsplit(".", 1)[-1].lower()
    ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}.get(ext)
    if not ctype:
        raise HTTPError(400, "Please upload a JPG, PNG or PDF")
    try:
        text = ai.read_document(f.data, f.filename, ctype, fields.get("language") or "en-IN")
        out = ai.chat_json([{"role": "system", "content": PRODUCT_PROMPT}, {"role": "user", "content": text[:20000]}])
    except ai.AIError:
        raise HTTPError(502, "Couldn't read the price list. Please add products manually.")
    drafts = []
    for it in (out.get("items") if isinstance(out, dict) else []) or []:
        if not isinstance(it, dict) or not str(it.get("name") or "").strip():
            continue
        try:
            price = int(round(float(it["price_rupees"]) * 100)) if it.get("price_rupees") is not None else None
            size = float(it["pack_size"]) if it.get("pack_size") is not None else None
        except (TypeError, ValueError):
            price, size = None, None
        drafts.append({"name": str(it["name"]).strip()[:100], "brand": str(it.get("brand") or "")[:60],
                       "category": str(it.get("category") or "Other")[:60], "pack_size": size,
                       "pack_unit": it.get("pack_unit") if it.get("pack_unit") in UNITS else "pcs",
                       "price_paise": price if price and price > 0 else None, "stock": 100})
    if not drafts:
        raise HTTPError(422, "Couldn't find any products in that file. Please add them manually.")
    return {"draft_items": drafts, "raw_text": text[:20000]}


@route("POST", "/api/store/seed-demo")
def store_seed_demo(req: Request):
    owner = _require_store(req)
    with db() as conn:
        if conn.execute("SELECT 1 FROM products WHERE store_id = ? AND deleted = 0", (owner["restaurant_id"],)).fetchone():
            raise HTTPError(409, "Your store already has products. Delete them first to load the demo catalogue.")
        for p in data()["demo_products"]:
            _insert_product(conn, owner["restaurant_id"], _product_in(dict(p, image_url="")))
    return {"ok": True, "added": len(data()["demo_products"])}


@route("GET", "/api/store/info")
def store_info(req: Request):
    owner = _require_store(req)
    with db() as conn:
        r = row(conn.execute("SELECT * FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone())
        n = conn.execute("SELECT COUNT(*) FROM products WHERE store_id = ? AND deleted = 0", (r["id"],)).fetchone()[0]
    base = m.public_base(req)
    return {"store": r, "products": n, "shop_url": f"{base}/s/{r['slug']}", "features": config.features()}


@route("GET", "/api/store/qr.svg")
def store_qr(req: Request):
    owner = _require_store(req)
    with db() as conn:
        slug = conn.execute("SELECT slug FROM restaurants WHERE id = ?", (owner["restaurant_id"],)).fetchone()[0]
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=1, image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(f"{m.public_base(req)}/s/{slug}")
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    return Response(buf.getvalue(), 200, "image/svg+xml; charset=utf-8", {"Cache-Control": "no-store"})


def _order_view(conn, o: dict) -> dict:
    items = rows(conn.execute("SELECT * FROM store_order_items WHERE order_id = ? ORDER BY id", (o["id"],)))
    return {"id": o["id"], "status": o["status"], "customer_name": o["customer_name"], "phone": o["phone"][-4:].rjust(10, "•"),
            "total_paise": o["total_paise"], "source": o["source"], "created_at": o["created_at"], "paid_at": o["paid_at"],
            "plan": json.loads(o["plan"]) if o["plan"] else None,
            "items": [{"name": i["name"], "packs": i["packs"], "pack_size": i["pack_size"], "pack_unit": i["pack_unit"],
                       "unit_price_paise": i["unit_price_paise"], "line_total_paise": i["packs"] * i["unit_price_paise"]} for i in items]}


@route("GET", "/api/store/orders")
def store_orders(req: Request):
    owner = _require_store(req)
    with db() as conn:
        _refresh_pending_orders(conn, owner["restaurant_id"])
        orders = rows(conn.execute("SELECT * FROM store_orders WHERE store_id = ? AND status IN ('PAID', 'PACKED', 'DONE', 'PENDING_PAYMENT') "
                                   "ORDER BY id DESC LIMIT 100", (owner["restaurant_id"],)))
        out = [_order_view(conn, o) for o in orders]
        ext = features.dashboard_extras(conn, owner["restaurant_id"])
    return {"orders": out, "announcements": ext["announcements"], "features": config.features()}


@route("POST", "/api/store/orders/{oid:int}/status")
def store_order_status(req: Request, oid: int):
    owner = _require_store(req)
    new = str(req.json().get("status") or "")
    flow = {"PAID": "PACKED", "PACKED": "DONE"}
    with db() as conn:
        o = row(conn.execute("SELECT * FROM store_orders WHERE id = ? AND store_id = ?", (oid, owner["restaurant_id"])).fetchone())
        if not o:
            raise HTTPError(404, "Order not found")
        if flow.get(o["status"]) != new:
            raise HTTPError(409, f"Can't move an order from {o['status'].lower()} to {new.lower()}.")
        conn.execute("UPDATE store_orders SET status = ? WHERE id = ?", (new, oid))
    return {"ok": True}


def store_sales(conn, store_id: int, date_str=None) -> dict:
    """A1 for supermarkets: only orders Cashfree confirmed as paid."""
    from .upgrades import _ist_hhmm, ist_day_bounds
    start, end, day = ist_day_bounds(date_str)
    orders = rows(conn.execute("SELECT * FROM store_orders WHERE store_id = ? AND paid_at >= ? AND paid_at < ? AND status IN ('PAID','PACKED','DONE')",
                               (store_id, start, end)))
    bills = [{"session_id": o["id"], "table": None, "label": f"Order #{o['id']}", "amount_paise": o["total_paise"], "method": "online",
              "link_id": o["link_id"], "settled_at": o["paid_at"], "time": _ist_hhmm(o["paid_at"])} for o in orders]
    items = []
    for o in orders:
        items += [{"name": i["name"], "qty": i["packs"], "unit_price_paise": i["unit_price_paise"]}
                  for i in rows(conn.execute("SELECT * FROM store_order_items WHERE order_id = ?", (o["id"],)))]
    out = summarize(bills, items)
    out["date"] = day
    return out


# ===================================================================== customer: shop + checkout

def _store_by_slug(conn, slug: str) -> dict:
    if not config.FEATURE_SUPERMARKET:
        _off()
    r = row(conn.execute("SELECT * FROM restaurants WHERE slug = ? AND business_type = 'supermarket'", (slug,)).fetchone())
    if not r:
        raise HTTPError(404, "Store not found")
    return r


@route("GET", "/s/{slug}")
def shop_page(req: Request, slug: str):
    if not config.FEATURE_SUPERMARKET:
        _off()
    return file_response(config.STATIC_DIR / "pages" / "shop.html")


@route("GET", "/s/{slug}/order/{oid:int}")
def shop_order_page(req: Request, slug: str, oid: int):
    if not config.FEATURE_SUPERMARKET:
        _off()
    return file_response(config.STATIC_DIR / "pages" / "shop.html")


@route("GET", "/store")
def store_page(req: Request):
    if not config.FEATURE_SUPERMARKET:
        _off()
    return file_response(config.STATIC_DIR / "pages" / "store.html")


@route("GET", "/credits")
def credits_page(req: Request):
    return file_response(config.STATIC_DIR / "pages" / "credits.html")


@route("GET", "/api/credits")
def credits(req: Request):
    return {"photos": [dict(v, key=k, thumb=(photo(k) or v)["thumb"]) for k, v in sorted(data()["photos"].items())],
            "nutrition_sources": sorted({i["source"] for i in data()["ingredients"].values()})}


@route("GET", "/api/s/{slug}")
def shop_info(req: Request, slug: str):
    with db() as conn:
        r = _store_by_slug(conn, slug)
        prods = [_with_photo(p) for p in _products(conn, r["id"], only_available=True)]
    f = config.features()
    return {"store": {"name": r["name"], "slug": r["slug"], "language": r["language"]},
            "products": [{k: p.get(k) for k in ("id", "name", "brand", "category", "pack_size", "pack_unit", "price_paise",
                                                 "image_url", "image_credit", "diet", "stock")} for p in prods],
            "categories": sorted({p["category"] for p in prods}),
            "features": {"meal_planner": f["meal_planner"], "voice": f["voice_order"], "online_payment": f["online_payment"],
                         "photos": f["photos"], "tts": f["server_tts"] or config.ai_ready()}}


def _create_order_link(req, conn_store: dict, order: dict) -> str:
    link_id = f"bs{order['id']}c{order['link_count'] + 1}{secrets.token_hex(2)}"
    base = m.public_base(req)
    link = cashfree.create_link(link_id, order["total_paise"], order["phone"], f"{conn_store['name']} - Order {order['id']}",
                                return_url=f"{base}/s/{conn_store['slug']}/order/{order['id']}?t={order['token']}",
                                notify_url=f"{base}/api/webhooks/cashfree")
    expires = (datetime.now(timezone.utc) + timedelta(minutes=29)).isoformat(timespec="seconds")
    with db() as conn:
        conn.execute("UPDATE store_orders SET link_id = ?, link_url = ?, link_count = link_count + 1, expires_at = ? WHERE id = ?",
                     (link_id, link["link_url"], expires, order["id"]))
    return link["link_url"]


@route("POST", "/api/s/{slug}/checkout")
def shop_checkout(req: Request, slug: str):
    d = req.json()
    phone = m._valid_phone(str(d.get("phone") or ""))
    name = str(d.get("name") or "").strip()[:60]
    lines = d.get("items")
    if not isinstance(lines, list) or not lines or len(lines) > 200:
        raise HTTPError(400, "Your cart is empty")
    if not config.cashfree_ready():
        raise HTTPError(503, "Online payment isn't set up for this store yet.")
    source = "planner" if d.get("source") == "planner" else "direct"
    plan = d.get("plan") if source == "planner" and isinstance(d.get("plan"), dict) else None
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store = _store_by_slug(conn, slug)
        prods = {p["id"]: p for p in _products(conn, store["id"], only_available=True)}
        merged: dict[int, int] = {}
        for line in lines:
            try:
                pid, packs = int(line.get("product_id")), int(line.get("packs"))
            except (TypeError, ValueError, AttributeError):
                raise HTTPError(400, "Bad cart line")
            if pid not in prods:
                raise HTTPError(409, "A product in your cart is no longer available. Please refresh.")
            if not 1 <= packs <= 50:
                raise HTTPError(400, "Quantity must be between 1 and 50")
            merged[pid] = merged.get(pid, 0) + packs
        for pid, k in merged.items():
            if k > prods[pid]["stock"]:
                raise HTTPError(409, f"Only {prods[pid]['stock']} of {prods[pid]['name']} left.")
        total = sum(prods[pid]["price_paise"] * k for pid, k in merged.items())  # prices from the database
        token = secrets.token_urlsafe(16)
        oid = conn.execute("INSERT INTO store_orders (store_id, status, customer_name, phone, total_paise, source, plan, token, created_at) "
                           "VALUES (?, 'PENDING_PAYMENT', ?, ?, ?, ?, ?, ?, ?)",
                           (store["id"], name, phone, total, source, json.dumps(plan, ensure_ascii=False) if plan else "",
                            token, now_iso())).lastrowid
        for pid, k in merged.items():
            p = prods[pid]
            conn.execute("INSERT INTO store_order_items (order_id, product_id, name, packs, pack_size, pack_unit, unit_price_paise) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", (oid, pid, p["name"], k, p["pack_size"], p["pack_unit"], p["price_paise"]))
        order = row(conn.execute("SELECT * FROM store_orders WHERE id = ?", (oid,)).fetchone())
    try:
        url = _create_order_link(req, store, order)
    except cashfree.CashfreeError as e:
        raise HTTPError(502, str(e))
    return {"order_id": oid, "token": token, "total_paise": total, "link_url": url}


def check_order_link(link_id: str) -> str:
    """Webhook / status check for a store order link. Paid only when Cashfree confirms the full amount. Idempotent."""
    with db() as conn:
        o = row(conn.execute("SELECT * FROM store_orders WHERE link_id = ?", (link_id,)).fetchone())
    if not o:
        return "UNKNOWN"
    if o["status"] != "PENDING_PAYMENT":
        return o["status"]
    try:
        link = cashfree.get_link(link_id)
    except cashfree.CashfreeError:
        return o["status"]
    if cashfree.is_paid(link, o["total_paise"]):
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("UPDATE store_orders SET status = 'PAID', paid_at = ? WHERE id = ? AND status = 'PENDING_PAYMENT'",
                               (now_iso(), o["id"]))
            if cur.rowcount:
                for it in rows(conn.execute("SELECT * FROM store_order_items WHERE order_id = ?", (o["id"],))):
                    conn.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (it["packs"], it["product_id"]))
                features.announce(conn, o["store_id"], o["id"], "store_order", amount_paise=o["total_paise"])
        return "PAID"
    return o["status"]


def _refresh_pending_orders(conn, store_id: int) -> None:
    for (lid,) in conn.execute("SELECT link_id FROM store_orders WHERE store_id = ? AND status = 'PENDING_PAYMENT' AND link_id IS NOT NULL "
                               "AND created_at >= ?", (store_id, (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())).fetchall():
        check_order_link(lid)


@route("GET", "/api/s/{slug}/orders/{oid:int}")
def shop_order(req: Request, slug: str, oid: int):
    t = req.query.get("t", "")
    with db() as conn:
        store = _store_by_slug(conn, slug)
        o = row(conn.execute("SELECT * FROM store_orders WHERE id = ? AND store_id = ?", (oid, store["id"])).fetchone())
    if not o or not secrets.compare_digest(o["token"], t):
        raise HTTPError(404, "Order not found")
    if o["status"] == "PENDING_PAYMENT" and o["link_id"]:
        check_order_link(o["link_id"])
    with db() as conn:
        o = row(conn.execute("SELECT * FROM store_orders WHERE id = ?", (oid,)).fetchone())
        v = _order_view(conn, o)
    v["link_url"] = o["link_url"] if o["status"] == "PENDING_PAYMENT" and o["expires_at"] > now_iso() else None
    return v


@route("POST", "/api/s/{slug}/orders/{oid:int}/repay")
def shop_order_repay(req: Request, slug: str, oid: int):
    t = str(req.json().get("t") or "")
    with db() as conn:
        store = _store_by_slug(conn, slug)
        o = row(conn.execute("SELECT * FROM store_orders WHERE id = ? AND store_id = ?", (oid, store["id"])).fetchone())
    if not o or not secrets.compare_digest(o["token"], t):
        raise HTTPError(404, "Order not found")
    if o["link_id"] and check_order_link(o["link_id"]) == "PAID":
        return {"paid": True}
    if o["status"] != "PENDING_PAYMENT":
        raise HTTPError(409, "This order can't be paid now.")
    if o["link_url"] and o["expires_at"] > now_iso():
        return {"link_url": o["link_url"]}
    try:
        return {"link_url": _create_order_link(req, store, o)}
    except cashfree.CashfreeError as e:
        raise HTTPError(502, str(e))


# ---------------- voice add for groceries

GROCERY_PROMPT = """A supermarket shopper says what they want to buy (Kannada, Hindi, English or mixed).
Reply with ONE JSON object only:
{"items": [{"name": string, "qty": number, "unit": "g" | "kg" | "ml" | "l" | "pcs" | "pack" | null}]}
Rules:
- Use product names from this list when they match: {NAMES}
- "2 kilo atta" -> {"name": "atta", "qty": 2, "unit": "kg"}; "one litre milk" -> qty 1, unit "l"; "6 eggs" -> qty 6, unit "pcs".
- "ondu", "eradu", "do", "ek" etc. are numbers. If no amount is said, qty 1 and unit "pack".
- Never invent prices or products they didn't ask for."""


def _families(prods: list[dict]) -> dict:
    """Group SKUs that are the same thing in different packs (same ingredient), keyed by searchable names."""
    ing = data()["ingredients"]
    fam: dict[str, list[dict]] = {}
    for p in prods:
        keys = {features._alias(re.sub(r"\d+(\.\d+)?\s*(kg|g|ml|l|pcs|L)\b", "", p["name"]))}
        if p.get("ingredient_id") and p["ingredient_id"] in ing:
            keys.add(features._alias(ing[p["ingredient_id"]]["name"]))
            keys.add(features._alias(p["ingredient_id"].replace("_", " ")))
        for k in keys:
            if k:
                fam.setdefault(k, []).append(p)
    return fam


def match_groceries(items: list, prods: list[dict]) -> tuple[list[dict], list[str]]:
    import difflib
    fam = _families(prods)
    keys = list(fam)
    lines, missing = {}, []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        said = features._alias(str(it.get("name") or ""))
        if not said:
            continue
        group = fam.get(said)
        if not group:
            words = set(said.split())
            owners = [k for k in keys if words and words <= set(k.split())]
            if owners:
                group = fam[min(owners, key=len)]
        if not group:
            close = difflib.get_close_matches(said, keys, n=1, cutoff=0.75)
            group = fam[close[0]] if close else None
        if not group:
            missing.append(str(it.get("name")))
            continue
        try:
            qty = float(it.get("qty") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        unit = str(it.get("unit") or "pack").lower()
        base_unit = group[0]["pack_unit"]
        conv = {"kg": ("g", 1000), "g": ("g", 1), "l": ("ml", 1000), "ml": ("ml", 1), "pcs": ("pcs", 1)}.get(unit)
        same_unit = [p for p in group if p["pack_unit"] == (conv[0] if conv else base_unit)]
        if conv and same_unit:
            need = qty * conv[1]
            res = planner.cover(need, [dict(p, stock=p["stock"]) for p in same_unit])
            if res:
                for pid, k in res[1].items():
                    lines[pid] = lines.get(pid, 0) + k
                continue
        # "a pack of X" or unit mismatch: that many of the most common (smallest) pack
        p = min(group, key=lambda x: (x["pack_size"], x["price_paise"]))
        lines[p["id"]] = lines.get(p["id"], 0) + max(1, min(50, int(round(qty))))
    by_id = {p["id"]: p for p in prods}
    out = [{"product_id": pid, "name": by_id[pid]["name"], "packs": k, "pack_size": by_id[pid]["pack_size"],
            "pack_unit": by_id[pid]["pack_unit"], "unit_price_paise": by_id[pid]["price_paise"],
            "line_total_paise": k * by_id[pid]["price_paise"], "image_url": _with_photo(by_id[pid]).get("image_url", "")}
           for pid, k in lines.items()]
    return out, missing


def _heard(req: Request) -> tuple[str, str]:
    fields, files = req.form()
    audio = files.get("audio")
    if audio is not None and audio.data:
        if len(audio.data) > 6_000_000:
            raise HTTPError(400, "That recording is too long.")
        try:
            h = ai.stt(audio.data, audio.filename or "voice.wav", audio.content_type or "audio/wav", fields.get("language") or None)
        except ai.AIError:
            raise HTTPError(502, "I couldn't hear that. Please try again or type it.")
        return h["transcript"], h.get("language_code") or "en-IN"
    text = (fields.get("text") or "").strip()[:400]
    if not text:
        raise HTTPError(400, "Say or type something.")
    return text, features._guess_lang(text)


@route("POST", "/api/s/{slug}/voice")
def shop_voice(req: Request, slug: str):
    if not config.features()["voice_order"]:
        _off()
    with db() as conn:
        store = _store_by_slug(conn, slug)
        prods = _products(conn, store["id"], only_available=True)
    transcript, lang = _heard(req)
    names = sorted({re.sub(r"\s+\d.*$", "", p["name"]) for p in prods})[:300]
    try:
        out = ai.chat_json([{"role": "system", "content": GROCERY_PROMPT.replace("{NAMES}", "; ".join(names))},
                            {"role": "user", "content": transcript}])
    except ai.AIError:
        return {"transcript": transcript, "lines": [], "missing": [], "total_paise": 0, "reply_text": "Sorry, I couldn't understand. Please search and tap instead.", "reply_audio": None}
    lines, missing = match_groceries(out.get("items") if isinstance(out, dict) else [], prods)
    total = sum(l["line_total_paise"] for l in lines)
    reply = (f"{len(lines)} item{'s' if len(lines) != 1 else ''}, {_rs(total)}. Add to your cart?" if lines
             else "I couldn't find those in this store. Please search instead.")
    if missing and lines:
        reply += f" Not found: {', '.join(missing)}."
    text, audio = features._localise(reply, lang)
    return {"transcript": transcript, "language": lang, "lines": lines, "missing": missing, "total_paise": total,
            "reply_text": text, "reply_audio": audio}


# ===================================================================== B2 meal planner

PLAN_PROMPT = """A shopper is planning meals. Extract what they said into ONE JSON object only:
{"people": int|null, "budget_rupees": number|null, "days": int|null,
 "meals": ["breakfast","lunch","dinner"]|null,
 "appliances": [one of: "gas_stove","induction","pressure_cooker","microwave","otg_oven","air_fryer","mixer_grinder","kettle","rice_cooker","tawa","kadai","toaster"]|null,
 "diet": "veg"|"egg"|"nonveg"|"vegan"|null,
 "goal": "high_protein"|"high_calorie"|"low_calorie"|"balanced"|"low_carb"|null}
Use null for anything not said. Never invent numbers."""


def _plan_in(d: dict) -> dict:
    try:
        people, days = int(d.get("people")), int(d.get("days"))
        budget = int(round(float(d.get("budget_rupees")) * 100))
    except (TypeError, ValueError):
        raise HTTPError(400, "Enter people, days and budget.")
    if not 1 <= people <= 20:
        raise HTTPError(400, "People must be between 1 and 20.")
    if not 1 <= days <= 7:
        raise HTTPError(400, "Days must be between 1 and 7.")
    if not 20000 <= budget <= 2_000_000:
        raise HTTPError(400, "Budget must be between ₹200 and ₹20,000.")
    meals = [x for x in (d.get("meals") or ["lunch", "dinner"]) if x in ("breakfast", "lunch", "dinner")] or ["lunch", "dinner"]
    appliances = [a for a in (d.get("appliances") or []) if a in planner.APPLIANCE_IDS]
    diet = d.get("diet") if d.get("diet") in planner.DIETS else "veg"
    goal = d.get("goal") if d.get("goal") in planner.GOALS else "balanced"
    return {"people": people, "days": days, "budget_paise": budget, "meals": meals, "appliances": appliances, "diet": diet,
            "goal": goal, "pantry": d.get("pantry", True) not in (False, 0, "0", "false")}


def _planner_store(conn, slug: str) -> dict:
    store = _store_by_slug(conn, slug)
    if not config.features()["meal_planner"]:
        _off()
    return store


def _recipe_card(r: dict, nutrition: dict, badges: list, people: int, prods: list[dict]) -> dict:
    ph = photo(f"recipe:{r['id']}")
    return {"id": r["id"], "name": r["name"], "name_local": r.get("name_local", {}), "meal": r["meal"], "diet": r["diet"],
            "time_min": r["time_min"], "appliances": sorted({a for g in r["appliances_any"] for a in g} | set(r["appliances_all"])),
            "nutrition": nutrition, "badges": badges,
            "cost_paise": planner.recipe_cost(r, people, prods, data()["ingredients"]),
            "photo": ph["thumb"] if ph else None, "photo_credit": f"{ph['author']} · {ph['license']}" if ph else None}


@route("GET", "/api/s/{slug}/planner/options")
def planner_options(req: Request, slug: str):
    with db() as conn:
        _planner_store(conn, slug)
    return {"appliances": [{"id": a, "label": l, "icon": i} for a, l, i in planner.APPLIANCES],
            "goals": [{"id": k, "label": v} for k, v in planner.GOALS.items()],
            "diets": [{"id": k, "label": v} for k, v in planner.DIETS.items()]}


@route("POST", "/api/s/{slug}/planner/recipes")
def planner_recipes(req: Request, slug: str):
    q = _plan_in(req.json())
    with db() as conn:
        store = _planner_store(conn, slug)
        prods = _products(conn, store["id"], only_available=True)
    D = data()
    allowed = planner.filter_recipes(D["recipes"], q["diet"], q["appliances"], q["meals"])
    ranked = planner.rank_recipes(allowed, D["ingredients"], q["goal"], limit=100)
    cards = [_recipe_card(x["recipe"], x["nutrition"], x["badges"], q["people"], prods) for x in ranked]
    return {"recipes": cards, "total_matching": len(allowed), "needed_slots": q["days"] * len(q["meals"]),
            "query": {k: v for k, v in q.items()}}


@route("GET", "/api/s/{slug}/planner/recipe/{rid}")
def planner_recipe(req: Request, slug: str, rid: str):
    try:
        people = max(1, min(20, int(req.query.get("people") or 4)))
    except ValueError:
        people = 4
    lang = req.query.get("lang") or "en-IN"
    with db() as conn:
        store = _planner_store(conn, slug)
        prods = _products(conn, store["id"], only_available=True)
    D = data()
    r = D["recipe_by_id"].get(rid)
    if not r:
        raise HTTPError(404, "Recipe not found")
    f = people / r["base_servings"]
    ings = []
    for line in r["ingredients"]:
        ing = D["ingredients"][line["id"]]
        q = line["qty"] * f
        ings.append({"id": ing["id"], "name": ing["name"], "name_local": ing.get("name_local", {}),
                     "qty": round(q) if ing["unit"] != "pcs" else round(q, 1), "unit": ing["unit"], "staple": ing["is_staple"]})
    steps = translate_many(r["steps"], lang) if lang != "en-IN" else r["steps"]
    n = planner.recipe_nutrition(r, D["ingredients"])
    card = _recipe_card(r, n, planner.badges(n), people, prods)
    from urllib.parse import quote_plus
    card.update(ingredients=ings, steps=steps, steps_en=r["steps"], people=people, lang=lang,
                youtube_search=f"https://www.youtube.com/results?search_query={quote_plus(r.get('youtube_query') or r['name'] + ' recipe')}",
                youtube_id=r.get("youtube_id"),
                nutrition_sources=sorted({D["ingredients"][l['id']]["source"] for l in r["ingredients"]}))
    return card


def translate(text: str, lang: str) -> str:
    """Translate once with the AI and cache it; falls back to English."""
    if lang not in features.LANG_NAMES or lang == "en-IN":
        return text
    with db() as conn:
        hit = conn.execute("SELECT text FROM translations WHERE lang = ? AND src = ?", (lang, text)).fetchone()
    if hit:
        return hit[0]
    try:
        out = ai.chat([{"role": "system", "content": f"Translate this cooking instruction into {features.LANG_NAMES[lang]}. Keep numbers, "
                                                     "times and temperatures as digits. Reply with the translation only."},
                       {"role": "user", "content": text}]).strip().strip('"')
    except ai.AIError:
        return text
    if out:
        with db() as conn:
            conn.execute("INSERT OR REPLACE INTO translations (lang, src, text) VALUES (?, ?, ?)", (lang, text, out))
    return out or text


def translate_many(texts: list[str], lang: str) -> list[str]:
    """Translate all steps of a recipe in ONE AI call (fast), cache each step; anything missing stays English."""
    if lang not in features.LANG_NAMES or lang == "en-IN" or not texts:
        return list(texts)
    with db() as conn:
        cached = {src: t for src, t in conn.execute(
            f"SELECT src, text FROM translations WHERE lang = ? AND src IN ({','.join('?' * len(texts))})", (lang, *texts)).fetchall()}
    todo = [t for t in dict.fromkeys(texts) if t not in cached]
    if todo:
        try:
            out = ai.chat_json([{"role": "system", "content": f"Translate each cooking instruction into {features.LANG_NAMES[lang]}. Keep numbers, "
                                                              "times and temperatures as digits. Reply with ONE JSON object only: "
                                                              '{"translations": [string, ...]} in the same order and the same count.'},
                                {"role": "user", "content": json.dumps(todo, ensure_ascii=False)}])
            got = out.get("translations") if isinstance(out, dict) else None
        except ai.AIError:
            got = None
        if isinstance(got, list) and len(got) == len(todo) and all(isinstance(x, str) and x.strip() for x in got):
            with db() as conn:
                for src, t in zip(todo, got):
                    conn.execute("INSERT OR REPLACE INTO translations (lang, src, text) VALUES (?, ?, ?)", (lang, src, t.strip()))
                    cached[src] = t.strip()
    return [cached.get(t, t) for t in texts]


@route("POST", "/api/s/{slug}/planner/cart")
def planner_cart(req: Request, slug: str):
    d = req.json()
    q = _plan_in(d)
    ids = [x for x in (d.get("recipe_ids") or []) if isinstance(x, str)][:60]
    with db() as conn:
        store = _planner_store(conn, slug)
        prods = _products(conn, store["id"], only_available=True)
    D = data()
    sel = [D["recipe_by_id"][x] for x in ids if x in D["recipe_by_id"]]
    if not sel:
        raise HTTPError(400, "Pick at least one recipe.")
    cart = planner.build_cart(sel, q["people"], prods, D["ingredients"], q["pantry"])
    # the shopper's edits: remove lines or swap a SKU for another pack/brand of the same ingredient
    removed = {int(x) for x in (d.get("removed_skus") or []) if str(x).isdigit()}
    swaps = {int(k): int(v) for k, v in (d.get("swaps") or {}).items() if str(k).isdigit() and str(v).isdigit()}
    by_id = {p["id"]: p for p in prods}
    lines = []
    for line in cart["lines"]:
        if line["sku"] in removed:
            continue
        if line["sku"] in swaps and swaps[line["sku"]] in by_id:
            alt = by_id[swaps[line["sku"]]]
            if alt.get("ingredient_id") == line["covers_ingredient"] and alt["pack_unit"] == line["pack_unit"]:
                k = max(1, -(-int(line["packs"] * line["pack_size"]) // int(alt["pack_size"])))
                line = dict(line, sku=alt["id"], name=alt["name"], brand=alt["brand"], packs=k, pack_size=alt["pack_size"],
                            unit_price=alt["price_paise"], line_total=k * alt["price_paise"])
        lines.append(line)
    cart = {"lines": lines, "total_paise": sum(l["line_total"] for l in lines), "missing": cart["missing"]}
    ctx = {"selected": sel, "people": q["people"], "ingredients": D["ingredients"], "pantry": q["pantry"]}
    fit = planner.fit_to_budget(cart, q["budget_paise"], prods, q["diet"], ctx)
    for line in cart["lines"]:  # other packs/brands the shopper could swap to
        line["alternatives"] = [{"sku": p["id"], "name": p["name"], "price_paise": p["price_paise"], "pack_size": p["pack_size"]}
                                for p in prods if p.get("ingredient_id") == line["covers_ingredient"] and p["id"] != line["sku"]
                                and p["pack_unit"] == line["pack_unit"]]
        line["image_url"] = _with_photo(by_id[line["sku"]]).get("image_url", "")
    fill = bool(d.get("fill"))
    total = fit["total_paise"] if fill and fit["ok"] else cart["total_paise"]
    return {"lines": cart["lines"], "missing": cart["missing"], "cart_total_paise": cart["total_paise"],
            "fit": fit, "filled": fill and fit["ok"], "total_paise": total, "budget_paise": q["budget_paise"],
            "message": planner.budget_message(total, q["budget_paise"]) if not (fill and fit["ok"]) else fit["message"],
            "coverage": planner.coverage(q["people"], q["days"], q["meals"], sel)}


@route("POST", "/api/s/{slug}/planner/voice")
def planner_voice(req: Request, slug: str):
    with db() as conn:
        _planner_store(conn, slug)
    if not config.ai_ready():
        _off()
    transcript, lang = _heard(req)
    try:
        out = ai.chat_json([{"role": "system", "content": PLAN_PROMPT}, {"role": "user", "content": transcript}])
    except ai.AIError:
        return {"transcript": transcript, "fields": {}, "error": "Sorry, I couldn't understand. Please tap the options."}
    out = out if isinstance(out, dict) else {}
    fields = {}
    for k, lo, hi in (("people", 1, 20), ("days", 1, 7)):
        try:
            v = int(out.get(k)) if out.get(k) is not None else None
        except (TypeError, ValueError):
            v = None
        if v is not None and lo <= v <= hi:
            fields[k] = v
    try:
        b = float(out.get("budget_rupees")) if out.get("budget_rupees") is not None else None
    except (TypeError, ValueError):
        b = None
    if b and 200 <= b <= 20000:
        fields["budget_rupees"] = b
    if isinstance(out.get("meals"), list):
        meals = [x for x in out["meals"] if x in ("breakfast", "lunch", "dinner")]
        if meals:
            fields["meals"] = meals
    if isinstance(out.get("appliances"), list):
        fields["appliances"] = [a for a in out["appliances"] if a in planner.APPLIANCE_IDS]
    if out.get("diet") in planner.DIETS:
        fields["diet"] = out["diet"]
    if out.get("goal") in planner.GOALS:
        fields["goal"] = out["goal"]
    return {"transcript": transcript, "language": lang, "fields": fields}


COMMANDS = {
    "next": r"\b(next|aage|agla|mundhe|munde|mundina)\b|ಮುಂದೆ|ಮುಂದಿನ|आगे|अगला",
    "previous": r"\b(previous|back|pichla|peeche|hinde|hindina)\b|ಹಿಂದೆ|ಹಿಂದಿನ|पिछला|पीछे",
    "repeat": r"\b(repeat|again|phir se|dobara|matte|innondu sala)\b|ಮತ್ತೆ|ಇನ್ನೊಮ್ಮೆ|फिर से|दोबारा",
    "stop": r"\b(stop|ruko|nillisu|band)\b|ನಿಲ್ಲಿಸು|रुको|बंद",
}


@route("POST", "/api/s/{slug}/planner/command")
def planner_command(req: Request, slug: str):
    """Hands-free cooking: 'next', 'repeat', 'previous' (any language), matched in code, no LLM."""
    with db() as conn:
        _planner_store(conn, slug)
    transcript, _ = _heard(req)
    t = transcript.lower()
    for cmd, pat in COMMANDS.items():
        if re.search(pat, t):
            return {"transcript": transcript, "command": cmd}
    return {"transcript": transcript, "command": None}


@route("POST", "/api/s/{slug}/tts")
def shop_tts(req: Request, slug: str):
    with db() as conn:
        _store_by_slug(conn, slug)
    if not config.ai_ready():
        _off()
    d = req.json()
    text = str(d.get("text") or "").strip()[:900]
    lang = d.get("lang") if d.get("lang") in features.LANG_NAMES else "en-IN"
    if not text:
        raise HTTPError(400, "Nothing to read")
    try:
        wav = ai.tts(text, lang)
    except ai.AIError:
        raise HTTPError(502, "Couldn't read aloud right now.")
    return {"audio": "data:audio/wav;base64," + base64.b64encode(wav).decode()}
