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

# (name, qty, unit, warn-at, note). Max 18 per section so every item gets its own shelf spot on the 3D map.
STARTER = {
    "Covers & packaging": [
        ("Parcel covers (small)", 200, "pcs", 50, "Carry bags for 1-2 items"), ("Parcel covers (medium)", 200, "pcs", 50, ""),
        ("Parcel covers (big)", 200, "pcs", 50, "Family orders"), ("Foil containers 250 ml", 100, "pcs", 25, "Chutney / sambar"),
        ("Foil containers 500 ml", 100, "pcs", 25, "Rice items"), ("Foil containers 750 ml", 100, "pcs", 25, "Meals"),
        ("Plastic containers with lids 500 ml", 100, "pcs", 25, "Microwave safe"), ("Paper bags", 150, "pcs", 40, ""),
        ("Butter paper", 2, "rolls", 1, "Dosa parcel wrap"), ("Aluminium foil roll", 2, "rolls", 1, "72 m"),
        ("Cling wrap", 2, "rolls", 1, ""), ("Chutney cups with lids", 300, "pcs", 80, "50 ml"),
        ("Sambar pouches", 300, "pcs", 80, "Heat-seal"), ("Rubber bands", 1, "kg", 0.2, ""),
        ("Parcel stickers", 500, "pcs", 100, "Restaurant name + phone"), ("Tape roll", 6, "rolls", 2, ""),
        ("Leaf wrap (banana leaf)", 100, "pcs", 30, "Keep moist")],
    "Disposables": [
        ("Paper cups 150 ml", 500, "pcs", 100, "Tea / coffee"), ("Paper cups 250 ml", 300, "pcs", 80, "Juice"),
        ("Wooden spoons", 500, "pcs", 100, ""), ("Plastic spoons", 300, "pcs", 80, "Takeaway only"),
        ("Areca leaf plates", 300, "pcs", 80, "Parcel meals"), ("Paper plates", 300, "pcs", 80, ""),
        ("Straws (paper)", 300, "pcs", 80, ""), ("Tissue paper", 30, "packs", 8, "Tables + counter"),
        ("Napkins", 20, "packs", 5, ""), ("Toothpicks", 10, "boxes", 3, ""), ("Bill wrapper envelopes", 200, "pcs", 50, "")],
    "Cookware": [
        ("Dosa tawa (big)", 2, "pcs", 0, "Cast iron, season weekly"), ("Dosa tawa (small)", 1, "pcs", 0, ""),
        ("Idli steamer", 2, "pcs", 0, "4-tier"), ("Idli plates", 8, "pcs", 0, ""), ("Pressure cooker 10 L", 2, "pcs", 0, "Check gasket monthly"),
        ("Pressure cooker gaskets", 4, "pcs", 1, "Spare"), ("Kadai (big)", 2, "pcs", 0, "Frying"), ("Kadai (small)", 2, "pcs", 0, "Tadka"),
        ("Stock pots", 3, "pcs", 0, "Sambar 20 L"), ("Vada maker", 1, "pcs", 0, ""), ("Wet grinder spare stone", 1, "pcs", 0, ""),
        ("Mixer jar (big)", 2, "pcs", 0, "Chutney"), ("Coffee filter (big)", 2, "pcs", 0, "Decoction")],
    "Utensils & tools": [
        ("Ladles", 10, "pcs", 0, ""), ("Dosa spatula", 4, "pcs", 0, "Flat steel"), ("Slotted spoons", 4, "pcs", 0, ""),
        ("Knives", 6, "pcs", 0, "Sharpen weekly"), ("Knife sharpener", 1, "pcs", 0, ""), ("Cutting boards", 4, "pcs", 0, "Green = veg"),
        ("Tongs", 4, "pcs", 0, ""), ("Peelers", 4, "pcs", 0, ""), ("Graters", 2, "pcs", 0, "Coconut"),
        ("Measuring cups", 2, "sets", 0, ""), ("Weighing scale", 1, "pcs", 0, "Calibrate monthly"), ("Strainers", 4, "pcs", 0, ""),
        ("Whisks", 2, "pcs", 0, ""), ("Batter buckets with lids", 6, "pcs", 0, "Idli / dosa batter")],
    "Serving ware": [
        ("Steel plates", 60, "pcs", 15, ""), ("Meal plates (thali)", 40, "pcs", 10, ""), ("Steel tumblers", 60, "pcs", 15, ""),
        ("Coffee davara set", 40, "sets", 10, "Tumbler + bowl"), ("Small bowls (katori)", 120, "pcs", 30, "Chutney / sambar"),
        ("Serving bowls", 30, "pcs", 8, ""), ("Serving spoons", 30, "pcs", 8, ""), ("Water jugs", 15, "pcs", 4, ""),
        ("Trays", 10, "pcs", 2, "Waiters"), ("Table bottles (water)", 20, "pcs", 5, "")],
    "Vegetables": [
        ("Onion", 25, "kg", 6, "Dry, airy rack"), ("Small onion (sambar)", 5, "kg", 1, ""), ("Tomato", 12, "kg", 3, ""),
        ("Potato", 20, "kg", 5, "Keep away from onion"), ("Carrot", 4, "kg", 1, ""), ("Beans", 3, "kg", 1, ""),
        ("Cabbage", 4, "kg", 1, ""), ("Capsicum", 2, "kg", 0.5, ""), ("Brinjal", 3, "kg", 1, ""), ("Drumstick", 2, "kg", 0.5, "Sambar"),
        ("Ladies finger", 2, "kg", 0.5, ""), ("Pumpkin", 3, "kg", 1, ""), ("Cucumber", 3, "kg", 1, "Salad / raita"),
        ("Beetroot", 2, "kg", 0.5, ""), ("Raw banana", 2, "kg", 0.5, "Bajji"), ("Garlic", 2, "kg", 0.5, ""),
        ("Ginger", 1.5, "kg", 0.3, "")],
    "Leafy & herbs": [
        ("Coriander leaves", 1, "kg", 0.3, "Fridge, wrap in cloth"), ("Curry leaves", 0.5, "kg", 0.1, ""), ("Mint leaves", 0.5, "kg", 0.1, ""),
        ("Green chilli", 2, "kg", 0.5, ""), ("Lemon", 60, "pcs", 15, ""), ("Spinach (palak)", 2, "kg", 0.5, "Use same day"),
        ("Methi leaves", 1, "kg", 0.3, ""), ("Spring onion", 1, "kg", 0.3, ""), ("Fresh coconut", 30, "pcs", 8, "Chutney")],
    "Fruits": [
        ("Banana", 3, "dozen", 1, "Kesari / juice"), ("Watermelon", 4, "pcs", 1, ""), ("Pineapple", 4, "pcs", 1, ""),
        ("Mosambi", 5, "kg", 1, "Juice"), ("Orange", 5, "kg", 1, ""), ("Apple", 3, "kg", 1, ""), ("Pomegranate", 2, "kg", 0.5, "")],
    "Rice, grains & rava": [
        ("Sona masoori rice", 75, "kg", 15, "Meals"), ("Idli rice", 50, "kg", 10, "Batter"), ("Basmati rice", 10, "kg", 3, "Pulao"),
        ("Idli rava", 20, "kg", 5, ""), ("Bombay rava (sooji)", 15, "kg", 4, "Upma / kesari"), ("Poha", 5, "kg", 1, ""),
        ("Vermicelli", 3, "kg", 1, ""), ("Sabudana", 2, "kg", 0.5, ""), ("Ragi", 5, "kg", 1, "Ragi mudde / dosa")],
    "Dals & pulses": [
        ("Urad dal", 20, "kg", 5, "Idli / vada batter"), ("Toor dal", 15, "kg", 4, "Sambar"), ("Chana dal", 8, "kg", 2, "Tadka / vada"),
        ("Moong dal", 5, "kg", 1, "Pongal"), ("Roasted gram (putani)", 3, "kg", 1, "Chutney"), ("Rajma", 2, "kg", 0.5, ""),
        ("Kabuli chana", 3, "kg", 1, "")],
    "Flours": [
        ("Wheat flour (atta)", 15, "kg", 4, "Chapathi"), ("Maida", 10, "kg", 3, "Parotta"), ("Besan (gram flour)", 5, "kg", 1, "Bajji"),
        ("Rice flour", 5, "kg", 1, "Crispy dosa"), ("Corn flour", 2, "kg", 0.5, "Gobi / manchurian"), ("Ragi flour", 3, "kg", 1, "")],
    "Spices & masala": [
        ("Turmeric powder", 1, "kg", 0.2, "Airtight"), ("Red chilli powder", 2, "kg", 0.5, ""), ("Kashmiri chilli powder", 1, "kg", 0.2, "Colour"),
        ("Coriander powder", 1, "kg", 0.2, ""), ("Sambar powder", 3, "kg", 1, ""), ("Rasam powder", 2, "kg", 0.5, ""),
        ("Garam masala", 0.5, "kg", 0.1, ""), ("Mustard seeds", 1, "kg", 0.2, ""), ("Jeera", 1, "kg", 0.2, ""),
        ("Pepper", 0.5, "kg", 0.1, "Pongal"), ("Fenugreek seeds", 0.5, "kg", 0.1, "Batter"), ("Dry red chillies", 2, "kg", 0.5, "Tadka"),
        ("Hing", 0.2, "kg", 0.05, "Strong smell, sealed jar"), ("Tamarind", 3, "kg", 1, "Sambar / rasam"), ("Jaggery", 5, "kg", 1, ""),
        ("Salt", 10, "kg", 2, ""), ("Sugar", 15, "kg", 4, ""), ("Cardamom", 0.2, "kg", 0.05, "Kesari / tea")],
    "Oil & ghee": [
        ("Sunflower oil", 30, "litre", 10, "Cooking"), ("Groundnut oil", 15, "litre", 5, "Frying"), ("Coconut oil", 5, "litre", 1, "Kerala dishes"),
        ("Ghee", 5, "kg", 1, "Ghee roast / pongal"), ("Butter (cooking)", 3, "kg", 1, "Benne dosa"), ("Sesame oil", 2, "litre", 0.5, "Podi")],
    "Dairy & cold room": [
        ("Milk", 25, "litre", 8, "Daily delivery, 2-6 °C"), ("Curd", 12, "kg", 3, "Curd rice / raita"), ("Paneer", 3, "kg", 1, ""),
        ("Butter (table)", 2, "kg", 0.5, ""), ("Cheese", 2, "kg", 0.5, "Cheese dosa"), ("Fresh cream", 1, "litre", 0.3, ""),
        ("Idli / dosa batter (ready)", 20, "kg", 5, "Use within 2 days"), ("Chutney (prepared)", 5, "kg", 1, "Same day only"),
        ("Ice cream tubs", 6, "tubs", 2, "Freezer -18 °C"), ("Frozen green peas", 3, "kg", 1, "Freezer")],
    "Beverages & sauces": [
        ("Filter coffee powder", 4, "kg", 1, "Airtight, away from heat"), ("Tea powder", 3, "kg", 1, ""), ("Boost / Horlicks", 2, "kg", 0.5, ""),
        ("Packaged water 1 L", 48, "bottles", 12, ""), ("Soft drinks", 48, "bottles", 12, ""), ("Tomato ketchup", 6, "bottles", 2, ""),
        ("Soy sauce", 2, "bottles", 1, "Chinese dishes"), ("Chilli sauce", 2, "bottles", 1, ""), ("Vinegar", 2, "litre", 0.5, ""),
        ("Pickle (mango)", 5, "kg", 1, ""), ("Rose syrup", 2, "bottles", 1, "Badam milk / juice"), ("Badam powder", 1, "kg", 0.3, "")],
    "Cleaning": [
        ("Dish wash liquid", 10, "litre", 2, ""), ("Dish wash bar", 20, "pcs", 5, ""), ("Floor cleaner", 10, "litre", 2, ""),
        ("Kitchen degreaser", 5, "litre", 1, "Chimney / stove"), ("Sanitiser (surfaces)", 5, "litre", 1, "Tables after every guest"),
        ("Hand wash", 5, "litre", 1, ""), ("Scrubbers (steel)", 20, "pcs", 5, ""), ("Sponges", 20, "pcs", 5, ""),
        ("Mops", 4, "pcs", 1, ""), ("Brooms", 4, "pcs", 1, ""), ("Garbage bags (big)", 100, "pcs", 20, "Wet waste"),
        ("Garbage bags (small)", 100, "pcs", 20, "Dry waste"), ("Table cloths / dusters", 40, "pcs", 10, "Wash daily"),
        ("Pest control spray", 2, "cans", 1, "Not near food")],
    "Gas, safety & staff": [
        ("LPG cylinder (commercial)", 3, "pcs", 1, "Book refill at 1 left"), ("Lighter / gas gun", 4, "pcs", 1, ""),
        ("Fire extinguisher", 2, "pcs", 0, "Check expiry date"), ("First-aid kit", 1, "kits", 0, "Burn cream, bandages"),
        ("Disposable gloves", 5, "boxes", 1, ""), ("Hair nets / caps", 100, "pcs", 20, ""), ("Aprons", 10, "pcs", 2, ""),
        ("Face masks", 100, "pcs", 20, ""), ("Bill paper rolls", 20, "rolls", 5, "Printer 80 mm"), ("Pens & order pads", 10, "pcs", 3, ""),
        ("Spare bulbs / tubes", 4, "pcs", 1, ""), ("Batteries (AA)", 12, "pcs", 4, "Remote / clock")],
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
        rid = owner["restaurant_id"]
        # First visit: the room opens already filled with the full list (192 items), ready to edit.
        if not conn.execute("SELECT storage_seeded FROM restaurants WHERE id = ?", (rid,)).fetchone()[0]:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT storage_seeded FROM restaurants WHERE id = ?", (rid,)).fetchone()[0]:
                _seed(conn, rid)
        return dict(_list(conn, rid), restaurant=owner["restaurant_name"])


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


def _seed(conn, rid: int) -> None:
    """Adds the full starter list (skips names already listed) and remembers it was done."""
    have = {r[0].lower() for r in conn.execute("SELECT name FROM storage_items WHERE restaurant_id = ?", (rid,))}
    ts = now_iso()
    for cat, items in STARTER.items():
        for name, qty, unit, low, note in items:
            if name.lower() not in have:
                conn.execute("INSERT INTO storage_items (restaurant_id, name, category, qty, unit, low_at, note, updated_at) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (rid, name, cat, qty, unit, low, note, ts))
    conn.execute("UPDATE restaurants SET storage_seeded = 1 WHERE id = ?", (rid,))


@route("POST", "/api/owner/storage/starter")
def storage_starter(req: Request):
    """One tap (re)fills the full kitchen list; items the owner already has are left alone."""
    _on()
    owner = m.require_owner(req)
    with db() as conn:
        _seed(conn, owner["restaurant_id"])
        return _list(conn, owner["restaurant_id"])


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
