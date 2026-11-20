"""Budget order ("Rs 800, dinner for 4") as a pure function: no AI, no database, easy to test.

Prices come in as integer paise from the menu. The result never exceeds the budget.
"""
import re

KINDS = ("main", "starter", "breakfast", "drink", "dessert", "snack", "other")

_KIND_RULES = [  # (kind, words found in the category or dish name), checked in this order
    ("drink", r"beverage|drink|coffee|kaapi|chai|tea\b|juice|lassi|soda|shake|milk|buttermilk|majjige|water|cola|smoothie"),
    ("dessert", r"dessert|sweet|ice ?cream|kulfi|halwa|jamun|payasa|kheer|mysore pak|ladoo|laddu|jalebi|cake|pastry"),
    ("starter", r"starter|appeti[sz]er|soup|salad|tikka|kebab|65\b"),
    ("snack", r"snack|chaat|puri|bajji|baje|bonda|pakora|samosa|buns?\b|vada pav|sandwich|fries"),
    ("breakfast", r"breakfast|tiffin|idli|idly|vada|upma|bath|pongal|poori|rotti|paratha|uttapam|khichdi"),
    ("main", r"main|meal|thali|rice|biryani|pulao|curry|dosa|dose|roti|naan|chapati|noodle|pasta|pizza|burger|anna|puliyogare"),
]


def kind_of(category: str, name: str = "") -> str:
    """Map a free-text menu category (and the dish name as a hint) to one of KINDS."""
    cat = (category or "").lower()
    for kind, pattern in _KIND_RULES:  # the category decides first
        if re.search(pattern, cat):
            return kind
    text = (name or "").lower()
    for kind, pattern in _KIND_RULES:  # then the dish name
        if re.search(pattern, text):
            return kind
    return "other"


def _line(item: dict, qty: int) -> dict:
    return {"menu_item_id": item["id"], "name": item["name"], "name_local": item.get("name_local", ""),
            "qty": qty, "unit_price_paise": item["price_paise"], "line_total_paise": item["price_paise"] * qty}


def _rupees(paise: int) -> str:
    return f"₹{paise // 100:,}" if paise % 100 == 0 else f"₹{paise / 100:,.2f}"


def build_budget_basket(menu_items: list[dict], budget_paise: int, people: int, meal: str | None = None) -> dict:
    """menu_items: dicts with id, name, price_paise, available, category (and optional name_local).

    Main course is required: the most expensive main whose price x people fits. Then, with what is left,
    one drink, one dessert and one starter (most expensive that fits, one per person). If money is still
    left, ONE suggestion is returned (never auto-added).
    """
    people = int(people)
    budget_paise = int(budget_paise)
    if people < 1 or budget_paise <= 0:
        return {"ok": False, "proposed_items": [], "total_paise": 0, "budget_paise": max(0, budget_paise),
                "remaining_paise": max(0, budget_paise), "suggestion": None, "min_budget_paise": None,
                "reply_text": "Tell me a budget and how many people are eating."}
    items = [m for m in menu_items if m.get("available", 1) and int(m.get("price_paise") or 0) > 0]
    by_kind: dict[str, list[dict]] = {k: [] for k in KINDS}
    for m in items:
        by_kind[kind_of(m.get("category", ""), m.get("name", ""))].append(m)

    meal = (meal or "").lower() or None
    if meal == "breakfast":
        main_order = ["breakfast", "main"]
    elif meal == "snacks":
        main_order = ["snack"]
    else:
        main_order = ["main"]

    main = None
    for kind in main_order:
        fits = [m for m in by_kind[kind] if m["price_paise"] * people <= budget_paise]
        if fits:
            main = max(fits, key=lambda m: (m["price_paise"], -m["id"]))
            break
    if main is None:
        pool = [m for k in main_order for m in by_kind[k]]
        if not pool:
            return {"ok": False, "proposed_items": [], "total_paise": 0, "budget_paise": budget_paise,
                    "remaining_paise": budget_paise, "suggestion": None, "min_budget_paise": None,
                    "reply_text": "This menu has no main dishes for that meal yet. Please order from the menu."}
        cheapest = min(m["price_paise"] for m in pool)
        need = cheapest * people
        return {"ok": False, "proposed_items": [], "total_paise": 0, "budget_paise": budget_paise,
                "remaining_paise": budget_paise, "suggestion": None, "min_budget_paise": need,
                "reply_text": f"For {people} {'person' if people == 1 else 'people'} the simplest option starts at {_rupees(need)}."}

    lines = [_line(main, people)]
    used = {main["id"]}
    remaining = budget_paise - main["price_paise"] * people
    for kind in ("drink", "dessert", "starter"):
        fits = [m for m in by_kind[kind] if m["id"] not in used and m["price_paise"] * people <= remaining]
        if fits:
            pick = max(fits, key=lambda m: (m["price_paise"], -m["id"]))
            lines.append(_line(pick, people))
            used.add(pick["id"])
            remaining -= pick["price_paise"] * people

    suggestion = None
    others = [m for m in items if m["id"] not in used and m["price_paise"] <= remaining]
    if others:
        def best_fill(m):
            qty = min(people, remaining // m["price_paise"])
            return qty * m["price_paise"], m["price_paise"], -m["id"]
        pick = max(others, key=best_fill)
        qty = min(people, remaining // pick["price_paise"])
        suggestion = _line(pick, qty)
        suggestion["text"] = (f"You have {_rupees(remaining)} left. Add {qty} {pick['name']} "
                              f"for {_rupees(qty * pick['price_paise'])}?")

    total = sum(l["line_total_paise"] for l in lines)
    assert total <= budget_paise
    names = ", ".join(f"{l['qty']} {l['name']}" for l in lines)
    reply = f"For {_rupees(budget_paise)}: {names}. Total {_rupees(total)}."
    if suggestion:
        reply += " " + suggestion["text"]
    return {"ok": True, "proposed_items": lines, "total_paise": total, "budget_paise": budget_paise,
            "remaining_paise": budget_paise - total, "suggestion": suggestion, "min_budget_paise": None,
            "reply_text": reply}
