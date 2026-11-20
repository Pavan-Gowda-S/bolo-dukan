"""AI Meal Planner maths: pure functions, no AI, no database.

Recipes and ingredients come from app/data/*.json; products are the store's SKUs (dicts).
Money is integer paise; quantities are grams, ml or pieces (the ingredient's own unit).
"""
import math

APPLIANCES = [
    ("gas_stove", "Gas stove", "🔥"), ("induction", "Induction", "⚡"), ("pressure_cooker", "Pressure cooker", "🍲"),
    ("microwave", "Microwave", "📡"), ("otg_oven", "OTG oven", "🔲"), ("air_fryer", "Air fryer", "🌪️"),
    ("mixer_grinder", "Mixer-grinder", "🌀"), ("kettle", "Electric kettle", "🫖"), ("rice_cooker", "Rice cooker", "🍚"),
    ("tawa", "Tawa", "🥘"), ("kadai", "Kadai", "🍳"), ("toaster", "Toaster / sandwich maker", "🥪"),
]
APPLIANCE_IDS = [a[0] for a in APPLIANCES]
GOALS = {"high_protein": "High protein", "high_calorie": "High calorie (weight gain)",
         "low_calorie": "Low calorie (weight loss)", "balanced": "Balanced", "low_carb": "Low carb"}
DIETS = {"veg": "Veg", "egg": "Egg (eggetarian)", "nonveg": "Non-veg", "vegan": "Vegan"}
MEALS = ["breakfast", "lunch", "dinner", "snacks"]


# ------------------------------------------------------------------ 1. filter

def diet_ok(recipe: dict, diet: str) -> bool:
    d = recipe.get("diet", "veg")
    if diet == "veg":
        return d in ("veg", "vegan")
    if diet == "egg":
        return d in ("veg", "vegan", "egg")
    if diet == "vegan":
        return d == "vegan" or bool(recipe.get("vegan_ok"))
    return True  # nonveg eats everything


def appliances_ok(recipe: dict, owned) -> bool:
    owned = set(owned or [])
    if not all(a in owned for a in recipe.get("appliances_all", [])):
        return False
    return all(any(a in owned for a in group) for group in recipe.get("appliances_any", []) if group)


def filter_recipes(recipes: list[dict], diet: str, appliances, meals) -> list[dict]:
    meals = set(meals or [])
    return [r for r in recipes
            if diet_ok(r, diet) and appliances_ok(r, appliances) and (not meals or meals & set(r.get("meal", [])))]


# ------------------------------------------------------------------ 2. nutrition

def _grams(ing: dict, qty: float) -> float:
    return qty * float(ing.get("grams_per_piece", 1)) if ing.get("unit") == "pcs" else qty


def recipe_nutrition(recipe: dict, ingredients: dict) -> dict:
    """Per serving: sum(qty x per_100 / 100) / base_servings. kcal to 1, grams to 0.1."""
    tot = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fibre_g": 0.0}
    for line in recipe["ingredients"]:
        ing = ingredients[line["id"]]
        g = _grams(ing, float(line["qty"]))
        for k in tot:
            tot[k] += g * float(ing["per_100"].get(k, 0)) / 100
    n = max(1, int(recipe.get("base_servings", 1)))
    return {"kcal": round(tot["kcal"] / n), **{k: round(tot[k] / n, 1) for k in ("protein_g", "carbs_g", "fat_g", "fibre_g")}}


# ------------------------------------------------------------------ 3. rank by goal

def goal_score(n: dict, goal: str) -> tuple:
    """Higher sorts first."""
    kcal = max(1, n["kcal"])
    if goal == "high_protein":
        return (n["protein_g"], n["protein_g"] * 100 / kcal)
    if goal == "high_calorie":
        return (n["kcal"], n["protein_g"])
    if goal == "low_calorie":
        return (1 if n["protein_g"] >= 10 else 0, -n["kcal"])
    if goal == "low_carb":
        return (1 if n["protein_g"] >= 10 else 0, -n["carbs_g"])
    # balanced: closest to 25% protein / 50% carbs / 25% fat of energy
    e = n["protein_g"] * 4 + n["carbs_g"] * 4 + n["fat_g"] * 9 or 1
    dist = abs(n["protein_g"] * 4 / e - .25) + abs(n["carbs_g"] * 4 / e - .5) + abs(n["fat_g"] * 9 / e - .25)
    return (-round(dist, 4), n["protein_g"])


def badges(n: dict) -> list[str]:
    out = []
    if n["protein_g"] >= 15:
        out.append("High protein")
    if n["kcal"] < 400:
        out.append("Under 400 kcal")
    if n["carbs_g"] < 20:
        out.append("Low carb")
    if n["fibre_g"] >= 6:
        out.append("High fibre")
    return out


def rank_recipes(recipes: list[dict], ingredients: dict, goal: str, limit: int = 100) -> list[dict]:
    scored = []
    for r in recipes:
        n = recipe_nutrition(r, ingredients)
        scored.append({"recipe": r, "nutrition": n, "badges": badges(n), "score": goal_score(n, goal)})
    scored.sort(key=lambda x: (x["score"], x["recipe"]["id"]), reverse=True)
    return scored[:limit]


# ------------------------------------------------------------------ 4. cost estimate (display only)

def _packs_for(ing_id: str, ing: dict, products: list[dict]) -> list[dict]:
    return [p for p in products if p.get("ingredient_id") == ing_id and p.get("available", 1)
            and int(p.get("stock", 0)) > 0 and p.get("pack_unit") == ing.get("unit") and float(p["pack_size"]) > 0]


def scaled_needs(recipes: list[dict], people: int, ingredients: dict, skip_staples: bool) -> dict:
    need: dict[str, float] = {}
    for r in recipes:
        f = people / max(1, int(r.get("base_servings", 1)))
        for line in r["ingredients"]:
            ing = ingredients[line["id"]]
            if skip_staples and ing.get("is_staple"):
                continue
            need[line["id"]] = need.get(line["id"], 0) + float(line["qty"]) * f
    return need


def recipe_cost(recipe: dict, people: int, products: list[dict], ingredients: dict, skip_staples: bool = True) -> int:
    """Estimated paise at the cheapest per-gram price (not whole packs)."""
    total = 0.0
    for ing_id, qty in scaled_needs([recipe], people, ingredients, skip_staples).items():
        packs = _packs_for(ing_id, ingredients[ing_id], products)
        if packs:
            total += qty * min(p["price_paise"] / float(p["pack_size"]) for p in packs)
    return int(round(total))


# ------------------------------------------------------------------ 5. build the cart

def cover(need: float, packs: list[dict]):
    """Cheapest multiset of packs whose sizes add up to >= need (respects stock).
    Returns (cost_paise, {product_id: count}, covered_qty) or None. Ties: less leftover, then fewer packs."""
    need = math.ceil(need - 1e-9)
    if need <= 0:
        return (0, {}, 0)
    packs = sorted(packs, key=lambda p: -float(p["pack_size"]))
    best = [None]

    def rec(i, remaining, cost, counts, covered, npacks):
        if remaining <= 0:
            key = (cost, covered - need, npacks)
            if best[0] is None or key < best[0][0]:
                best[0] = (key, dict(counts), covered)
            return
        if i == len(packs) or (best[0] and cost >= best[0][0][0]):
            return
        p = packs[i]
        size = float(p["pack_size"])
        max_k = min(int(p.get("stock", 0)), math.ceil(remaining / size))
        for k in range(max_k, -1, -1):
            if k:
                counts[p["id"]] = k
            rec(i + 1, remaining - k * size, cost + k * p["price_paise"], counts, covered + k * size, npacks + k)
            counts.pop(p["id"], None)

    rec(0, need, 0, {}, 0, 0)
    if best[0] is None:
        return None
    (cost, _, _), counts, covered = best[0]
    return cost, counts, covered


def build_cart(selected: list[dict], people: int, products: list[dict], ingredients: dict, pantry_has_staples: bool) -> dict:
    by_id = {p["id"]: p for p in products}
    lines, missing = [], []
    for ing_id, qty in sorted(scaled_needs(selected, people, ingredients, pantry_has_staples).items()):
        ing = ingredients[ing_id]
        res = cover(qty, _packs_for(ing_id, ing, products))
        if res is None:
            missing.append({"ingredient": ing_id, "name": ing["name"], "needed_qty": math.ceil(qty), "unit": ing["unit"]})
            continue
        cost, counts, covered = res
        for pid, k in sorted(counts.items()):
            p = by_id[pid]
            lines.append({"sku": pid, "name": p["name"], "brand": p.get("brand", ""), "packs": k,
                          "pack_size": p["pack_size"], "pack_unit": p["pack_unit"], "unit_price": p["price_paise"],
                          "line_total": k * p["price_paise"], "covers_ingredient": ing_id, "ingredient_name": ing["name"],
                          "needed_qty": math.ceil(qty), "leftover_qty": round(covered - math.ceil(qty), 1)})
    return {"lines": lines, "total_paise": sum(l["line_total"] for l in lines), "missing": missing}


# ------------------------------------------------------------------ 6. fit to budget

def topup_ok(product: dict, diet: str) -> bool:
    d = product.get("diet", "veg")
    allowed = {"veg": ("veg", "vegan"), "egg": ("veg", "vegan", "egg"), "vegan": ("vegan",)}.get(diet)
    return allowed is None or d in allowed


def _rs(paise: int) -> str:
    return f"₹{paise // 100:,}" if paise % 100 == 0 else f"₹{paise / 100:,.2f}"


def budget_message(total: int, budget: int) -> str:
    if total > budget:
        return f"Your cart: {_rs(total)}, which is {_rs(total - budget)} over your {_rs(budget)} budget."
    return f"Your cart: {_rs(total)}, {_rs(budget - total)} under your {_rs(budget)} budget."


def best_topups(gap_min: int, gap_max: int, room: int, candidates: list[dict], max_items: int = 6, max_each: int = 3):
    """Pick top-up packs adding between gap_min and gap_max paise (never more than `room`).
    If impossible, get as close as possible without exceeding `room`. Returns (added_paise, {pid: count})."""
    states = {0: (0, ())}  # sum -> (item count, ((pid, count), ...))
    for p in sorted(candidates, key=lambda x: (x["price_paise"], x["id"])):
        price = int(p["price_paise"])
        if price <= 0:
            continue
        cap = min(max_each, int(p.get("stock", 0)))
        new = dict(states)
        for s, (n, combo) in states.items():
            for k in range(1, cap + 1):
                t, nn = s + k * price, n + k
                if t > room or nn > max_items:
                    break
                if t not in new or nn < new[t][0]:
                    new[t] = (nn, combo + ((p["id"], k),))
        states = new

    def miss(s):
        return max(0, gap_min - s) + max(0, s - gap_max)
    best = min(states, key=lambda s: (miss(s), states[s][0], -s))
    return best, dict(states[best][1])


def fit_to_budget(cart: dict, budget_paise: int, products: list[dict], diet: str, context: dict | None = None) -> dict:
    """Target: [budget - 30, budget - 20] rupees. Never goes over budget, never silently drops anything."""
    total, budget = int(cart["total_paise"]), int(budget_paise)
    lo, hi = budget - 3000, budget - 2000
    out = {"ok": True, "total_paise": total, "budget_paise": budget, "window": [lo, hi], "add": [],
           "added_paise": 0, "suggestions": [], "over_paise": 0, "in_window": lo <= total <= hi}
    if total > budget:
        out.update(ok=False, over_paise=total - budget)
        sug = []
        if context:  # removing a recipe: how much would it save?
            sel = context["selected"]
            for r in sel:
                rest = [x for x in sel if x["id"] != r["id"]]
                t2 = build_cart(rest, context["people"], products, context["ingredients"], context["pantry"])["total_paise"]
                if t2 < total:
                    sug.append({"type": "remove_recipe", "recipe_id": r["id"], "name": r["name"], "saves_paise": total - t2,
                                "fixes": t2 <= budget, "text": f"Remove {r['name']} to save {_rs(total - t2)}"})
        for line in cart["lines"]:  # a cheaper product for the same ingredient (e.g. after a manual swap)
            alts = [p for p in products if p.get("ingredient_id") == line["covers_ingredient"] and p["id"] != line["sku"]
                    and p.get("available", 1) and int(p.get("stock", 0)) > 0]
            for p in alts:
                k = math.ceil(line["packs"] * line["pack_size"] / float(p["pack_size"]))
                if k <= int(p.get("stock", 0)) and k * p["price_paise"] < line["line_total"]:
                    sug.append({"type": "swap", "from_sku": line["sku"], "to_sku": p["id"], "packs": k,
                                "saves_paise": line["line_total"] - k * p["price_paise"],
                                "text": f"Swap {line['name']} for {k} × {p['name']} to save {_rs(line['line_total'] - k * p['price_paise'])}"})
        out["suggestions"] = sorted(sug, key=lambda s: -s["saves_paise"])[:8]
        out["message"] = budget_message(total, budget) + " Remove a recipe or swap a pack to fit."
        return out
    if total < lo:
        cands = [p for p in products if p.get("topup") and p.get("available", 1) and int(p.get("stock", 0)) > 0 and topup_ok(p, diet)]
        added, combo = best_topups(lo - total, hi - total, budget - total, cands)
        by_id = {p["id"]: p for p in products}
        out["add"] = [{"sku": pid, "name": by_id[pid]["name"], "packs": k, "pack_size": by_id[pid]["pack_size"],
                       "pack_unit": by_id[pid]["pack_unit"], "unit_price": by_id[pid]["price_paise"],
                       "line_total": k * by_id[pid]["price_paise"]} for pid, k in combo.items()]
        out["added_paise"] = added
        out["total_paise"] = total + added
        out["in_window"] = lo <= total + added <= hi
    assert out["total_paise"] <= budget
    out["message"] = budget_message(out["total_paise"], budget)
    return out


# ------------------------------------------------------------------ 7. coverage

def coverage(people: int, days: int, meals: list[str], selected: list[dict]) -> dict:
    slots_needed = days * len([x for x in meals if x in ("breakfast", "lunch", "dinner")])
    chosen = sum(1 for r in selected if set(r.get("meal", [])) & set(meals) & {"breakfast", "lunch", "dinner"})
    return {"slots_needed": slots_needed, "slots_chosen": chosen, "servings_needed": slots_needed * people,
            "servings_chosen": chosen * people,
            "text": (f"You've chosen meals for {chosen} of {slots_needed} needed "
                     f"({people} people × {days} day{'s' if days != 1 else ''} × {len(meals)} meal{'s' if len(meals) != 1 else ''} a day "
                     f"= {slots_needed * people} servings).")}
