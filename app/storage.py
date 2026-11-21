"""Restaurant storage room finder: the owner lists what is in the store room (covers, utensils, vegetables…)
by section, and anyone with the owner login can type "parcel cover" and see the exact rack in 3D.

Same 3D map as the supermarket aisle finder (static/js/store3d.js): each section is one side of a rack row,
items A-Z, 3 shelves per bay. Quantities and a low-stock level are optional and only used for the "running low" badge.
Switch: FEATURE_STORAGE_FINDER.
"""
from . import config
from . import main as m
from .db import db, now_iso, row, rows
from .web import HTTPError, Request, file_response

route = m.app.route
MAX_ITEMS = 500

STARTER = {
    "Covers & packaging": [("Parcel covers (small)", 200, "pcs", 50), ("Parcel covers (big)", 200, "pcs", 50),
                           ("Foil containers 500 ml", 100, "pcs", 25), ("Paper bags", 150, "pcs", 40),
                           ("Butter paper", 2, "rolls", 1), ("Tissue paper", 20, "packs", 5),
                           ("Cling wrap", 2, "rolls", 1), ("Chutney cups with lids", 300, "pcs", 80),
                           ("Sambar pouches", 300, "pcs", 80)],
    "Utensils & tools": [("Dosa tawa", 2, "pcs", 0), ("Ladles", 8, "pcs", 0), ("Steel plates", 40, "pcs", 10),
                         ("Steel tumblers", 40, "pcs", 10), ("Idli plates", 6, "pcs", 0), ("Serving bowls", 30, "pcs", 8),
                         ("Knives", 6, "pcs", 0), ("Cutting boards", 3, "pcs", 0), ("Tongs", 4, "pcs", 0)],
    "Vegetables": [("Onion", 20, "kg", 5), ("Tomato", 10, "kg", 3), ("Potato", 15, "kg", 4), ("Green chilli", 2, "kg", 0.5),
                   ("Coriander leaves", 1, "kg", 0.3), ("Curry leaves", 0.5, "kg", 0.1), ("Carrot", 4, "kg", 1),
                   ("Beans", 3, "kg", 1), ("Ginger", 1, "kg", 0.3)],
    "Dry goods & grains": [("Rice", 50, "kg", 10), ("Idli rava", 20, "kg", 5), ("Urad dal", 15, "kg", 4), ("Toor dal", 10, "kg", 3),
                           ("Wheat flour", 10, "kg", 3), ("Sugar", 10, "kg", 3), ("Salt", 5, "kg", 1), ("Poha", 5, "kg", 1)],
    "Spices & masala": [("Turmeric powder", 1, "kg", 0.2), ("Chilli powder", 2, "kg", 0.5), ("Mustard seeds", 1, "kg", 0.2),
                        ("Sambar powder", 3, "kg", 1), ("Rasam powder", 2, "kg", 0.5), ("Jeera", 1, "kg", 0.2), ("Hing", 0.2, "kg", 0.05)],
    "Oil & ghee": [("Sunflower oil", 30, "litre", 10), ("Ghee", 5, "kg", 1), ("Coconut oil", 5, "litre", 1)],
    "Dairy & cold": [("Milk", 20, "litre", 5), ("Curd", 10, "kg", 3), ("Paneer", 3, "kg", 1), ("Butter", 2, "kg", 0.5)],
    "Beverages": [("Coffee powder", 3, "kg", 1), ("Tea powder", 2, "kg", 0.5)],
    "Cleaning": [("Dish wash liquid", 5, "litre", 1), ("Floor cleaner", 5, "litre", 1), ("Scrubbers", 20, "pcs", 5),
                 ("Garbage bags", 100, "pcs", 20), ("Hand wash", 3, "litre", 1)],
}


def _on():
    if not config.FEATURE_STORAGE_FINDER:
        raise HTTPError(404, "Not found")


def _clean(body: dict, partial: bool = False) -> dict:
    out = {}
    for key, limit in (("name", 60), ("category", 40), ("unit", 12), ("note", 120)):
        if key in body or not partial:
            v = " ".join(str(body.get(key) or "").split())
            if key in ("name", "category") and not v:
                raise HTTPError(400, f"Please give the item a {'name' if key == 'name' else 'section (e.g. Vegetables)'}.")
            if len(v) > limit:
                raise HTTPError(400, f"{key.capitalize()} is too long (max {limit} letters).")
            out[key] = v
    for key in ("qty", "low_at"):
        if key in body or not partial:
            try:
                v = float(body.get(key) or 0)
            except (TypeError, ValueError):
                raise HTTPError(400, "Quantity must be a number.")
            if not (0 <= v <= 1_000_000):
                raise HTTPError(400, "Quantity must be between 0 and 10,00,000.")
            out[key] = round(v, 3)
    return out


def _list(conn, rid: int) -> dict:
    items = rows(conn.execute("SELECT id, name, category, qty, unit, low_at, note FROM storage_items WHERE restaurant_id = ? "
                              "ORDER BY category, name COLLATE NOCASE", (rid,)))
    for i in items:
        i["low"] = i["low_at"] > 0 and i["qty"] <= i["low_at"]
    return {"items": items, "categories": sorted({i["category"] for i in items}, key=str.lower),
            "low": sum(1 for i in items if i["low"])}


def _mine(conn, rid: int, item_id: int) -> dict:
    it = row(conn.execute("SELECT * FROM storage_items WHERE id = ? AND restaurant_id = ?", (item_id, rid)).fetchone())
    if it is None:
        raise HTTPError(404, "Item not found")
    return it


@route("GET", "/owner/storage")
def storage_page(req: Request):
    _on()
    return file_response(config.STATIC_DIR / "pages" / "storage.html")


@route("GET", "/api/owner/storage")
def storage_list(req: Request):
    _on()
    owner = m.require_owner(req)
    with db() as conn:
        return dict(_list(conn, owner["restaurant_id"]), restaurant=owner["restaurant_name"])


@route("POST", "/api/owner/storage")
def storage_add(req: Request):
    _on()
    owner = m.require_owner(req)
    it = _clean(req.json())
    with db() as conn:
        rid = owner["restaurant_id"]
        if conn.execute("SELECT COUNT(*) FROM storage_items WHERE restaurant_id = ?", (rid,)).fetchone()[0] >= MAX_ITEMS:
            raise HTTPError(400, f"The storage list is full ({MAX_ITEMS} items).")
        if conn.execute("SELECT 1 FROM storage_items WHERE restaurant_id = ? AND lower(name) = lower(?)", (rid, it["name"])).fetchone():
            raise HTTPError(409, f"“{it['name']}” is already in the list.")
        conn.execute("INSERT INTO storage_items (restaurant_id, name, category, qty, unit, low_at, note, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (rid, it["name"], it["category"], it["qty"], it["unit"], it["low_at"], it["note"], now_iso()))
        return _list(conn, rid)


@route("POST", "/api/owner/storage/starter")
def storage_starter(req: Request):
    """One tap fills a typical South Indian kitchen store room; skips names already listed."""
    _on()
    owner = m.require_owner(req)
    with db() as conn:
        rid = owner["restaurant_id"]
        have = {r[0].lower() for r in conn.execute("SELECT name FROM storage_items WHERE restaurant_id = ?", (rid,))}
        ts = now_iso()
        for cat, items in STARTER.items():
            for name, qty, unit, low in items:
                if name.lower() not in have:
                    conn.execute("INSERT INTO storage_items (restaurant_id, name, category, qty, unit, low_at, note, updated_at) "
                                 "VALUES (?, ?, ?, ?, ?, ?, '', ?)", (rid, name, cat, qty, unit, low, ts))
        return _list(conn, rid)


@route("POST", "/api/owner/storage/{item_id:int}")
def storage_update(req: Request, item_id: int):
    _on()
    owner = m.require_owner(req)
    ch = _clean(req.json(), partial=True)
    with db() as conn:
        rid = owner["restaurant_id"]
        _mine(conn, rid, item_id)
        if "name" in ch and conn.execute("SELECT 1 FROM storage_items WHERE restaurant_id = ? AND lower(name) = lower(?) AND id != ?",
                                         (rid, ch["name"], item_id)).fetchone():
            raise HTTPError(409, f"“{ch['name']}” is already in the list.")
        if ch:
            conn.execute(f"UPDATE storage_items SET {', '.join(k + ' = ?' for k in ch)}, updated_at = ? WHERE id = ?",
                         (*ch.values(), now_iso(), item_id))
        return _list(conn, rid)


@route("POST", "/api/owner/storage/{item_id:int}/delete")
def storage_delete(req: Request, item_id: int):
    _on()
    owner = m.require_owner(req)
    with db() as conn:
        _mine(conn, owner["restaurant_id"], item_id)
        conn.execute("DELETE FROM storage_items WHERE id = ?", (item_id,))
        return _list(conn, owner["restaurant_id"])
