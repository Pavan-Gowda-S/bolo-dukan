"""Sales summary as a pure function (no database): totals come only from verified-paid bills."""


def summarize(bills: list[dict], items: list[dict], top_n: int = 3) -> dict:
    """bills: [{session_id, table, amount_paise, method ('online'|'cash'|'split'), link_id, settled_at}]
    items: [{name, qty, unit_price_paise}] sold on those bills (free items are ignored for 'top items')."""
    collected = sum(int(b["amount_paise"]) for b in bills)
    count = len(bills)
    online = [b for b in bills if b["method"] in ("online", "split")]
    cash = [b for b in bills if b["method"] == "cash"]
    qty: dict[str, int] = {}
    for it in items:
        if int(it.get("unit_price_paise") or 0) <= 0:
            continue
        qty[it["name"]] = qty.get(it["name"], 0) + int(it["qty"])
    top = sorted(qty.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    return {
        "collected_paise": collected,
        "bills": count,
        "average_paise": collected // count if count else 0,
        "online_paise": sum(int(b["amount_paise"]) for b in online),
        "cash_paise": sum(int(b["amount_paise"]) for b in cash),
        "online_count": len(online),
        "cash_count": len(cash),
        "top_items": [{"name": n, "qty": q} for n, q in top],
        "bill_list": sorted(bills, key=lambda b: b["settled_at"]),
    }
