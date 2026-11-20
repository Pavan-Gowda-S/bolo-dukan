import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import planner as P  # noqa: E402

ING = {
    "toor_dal": {"id": "toor_dal", "name": "Toor dal", "unit": "g", "per_100": {"kcal": 343, "protein_g": 22.3, "carbs_g": 57.6, "fat_g": 1.7, "fibre_g": 9.1}, "is_staple": False},
    "tomato": {"id": "tomato", "name": "Tomato", "unit": "g", "per_100": {"kcal": 22, "protein_g": 0.9, "carbs_g": 3.6, "fat_g": 0.2, "fibre_g": 1.4}, "is_staple": False},
    "ghee": {"id": "ghee", "name": "Ghee", "unit": "g", "per_100": {"kcal": 900, "protein_g": 0, "carbs_g": 0, "fat_g": 99.5, "fibre_g": 0}, "is_staple": False},
    "salt": {"id": "salt", "name": "Salt", "unit": "g", "per_100": {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fibre_g": 0}, "is_staple": True},
    "egg": {"id": "egg", "name": "Egg", "unit": "pcs", "grams_per_piece": 50, "per_100": {"kcal": 143, "protein_g": 12.6, "carbs_g": 0.7, "fat_g": 9.5, "fibre_g": 0}, "is_staple": False},
    "paneer": {"id": "paneer", "name": "Paneer", "unit": "g", "per_100": {"kcal": 265, "protein_g": 18.3, "carbs_g": 1.2, "fat_g": 20.8, "fibre_g": 0}, "is_staple": False},
}
DAL = {"id": "dal_tadka", "name": "Dal Tadka", "meal": ["lunch", "dinner"], "diet": "veg", "vegan_ok": False,
       "appliances_any": [["gas_stove", "induction"]], "appliances_all": ["pressure_cooker"], "base_servings": 4,
       "ingredients": [{"id": "toor_dal", "qty": 200}, {"id": "tomato", "qty": 150}, {"id": "ghee", "qty": 20}, {"id": "salt", "qty": 8}]}
OMELETTE = {"id": "omelette", "name": "Omelette", "meal": ["breakfast"], "diet": "egg", "appliances_any": [["gas_stove", "induction"], ["tawa", "kadai"]],
            "appliances_all": [], "base_servings": 2, "ingredients": [{"id": "egg", "qty": 4}]}
SAMBAR = {"id": "sambar", "name": "Sambar", "meal": ["lunch", "dinner"], "diet": "vegan", "appliances_any": [["gas_stove", "induction"]],
          "appliances_all": [], "base_servings": 4, "ingredients": [{"id": "toor_dal", "qty": 150}, {"id": "tomato", "qty": 200}]}
CHICKEN = {"id": "chicken", "name": "Chicken curry", "meal": ["dinner"], "diet": "nonveg", "appliances_any": [["gas_stove"]],
           "appliances_all": [], "base_servings": 4, "ingredients": [{"id": "tomato", "qty": 100}]}
PANEER = {"id": "paneer_bhurji", "name": "Paneer bhurji", "meal": ["dinner"], "diet": "veg", "appliances_any": [["gas_stove"]],
          "appliances_all": [], "base_servings": 2, "ingredients": [{"id": "paneer", "qty": 200}, {"id": "tomato", "qty": 100}]}
RECIPES = [DAL, OMELETTE, SAMBAR, CHICKEN, PANEER]


def prod(i, ing, size, rupees, unit="g", stock=50, topup=0, diet="veg", name=None):
    return {"id": i, "name": name or f"{ing} {size}{unit}", "ingredient_id": ing, "pack_size": size, "pack_unit": unit,
            "price_paise": rupees * 100, "stock": stock, "available": 1, "topup": topup, "diet": diet}


PRODUCTS = [prod(1, "toor_dal", 500, 55), prod(2, "toor_dal", 1000, 95), prod(3, "tomato", 1000, 40), prod(4, "tomato", 500, 22),
            prod(5, "ghee", 200, 130), prod(6, "ghee", 500, 300), prod(7, "egg", 6, 48, "pcs", diet="egg"), prod(8, "egg", 12, 90, "pcs", diet="egg"),
            prod(9, "paneer", 200, 90), prod(10, "salt", 1000, 28)]


class FilterTests(unittest.TestCase):
    def test_diet(self):
        ids = lambda d: {r["id"] for r in P.filter_recipes(RECIPES, d, P.APPLIANCE_IDS, None)}
        self.assertEqual(ids("veg"), {"dal_tadka", "sambar", "paneer_bhurji"})
        self.assertEqual(ids("egg"), {"dal_tadka", "sambar", "paneer_bhurji", "omelette"})
        self.assertEqual(ids("vegan"), {"sambar"})
        self.assertEqual(ids("nonveg"), {r["id"] for r in RECIPES})

    def test_appliances(self):
        got = {r["id"] for r in P.filter_recipes(RECIPES, "nonveg", ["induction"], None)}
        self.assertEqual(got, {"sambar"})  # dal needs a pressure cooker, omelette needs tawa/kadai, others need gas
        got = {r["id"] for r in P.filter_recipes(RECIPES, "nonveg", ["gas_stove", "pressure_cooker"], None)}
        self.assertEqual(got, {"dal_tadka", "sambar", "chicken", "paneer_bhurji"})

    def test_meals(self):
        got = {r["id"] for r in P.filter_recipes(RECIPES, "nonveg", P.APPLIANCE_IDS, ["breakfast"])}
        self.assertEqual(got, {"omelette"})


class NutritionTests(unittest.TestCase):
    def test_dal(self):
        n = P.recipe_nutrition(DAL, ING)
        kcal = (200 * 343 + 150 * 22 + 20 * 900) / 100 / 4
        prot = (200 * 22.3 + 150 * 0.9) / 100 / 4
        self.assertEqual(n["kcal"], round(kcal))
        self.assertEqual(n["protein_g"], round(prot, 1))

    def test_pieces_use_grams(self):
        n = P.recipe_nutrition(OMELETTE, ING)  # 4 eggs x 50 g = 200 g over 2 servings
        self.assertEqual(n["kcal"], round(200 * 143 / 100 / 2))

    def test_rank(self):
        r = P.rank_recipes(RECIPES, ING, "high_protein")
        prots = [x["nutrition"]["protein_g"] for x in r]
        self.assertEqual(prots, sorted(prots, reverse=True))
        low = P.rank_recipes(RECIPES, ING, "low_calorie")
        self.assertTrue(all("badges" in x for x in low))
        self.assertLessEqual(len(P.rank_recipes(RECIPES * 30, ING, "balanced")), 100)


class CartTests(unittest.TestCase):
    def test_cover_prefers_bigger_cheaper_pack(self):
        cost, counts, covered = P.cover(700, [prod(1, "x", 500, 55), prod(2, "x", 1000, 95)])
        self.assertEqual((cost, counts), (9500, {2: 1}))
        cost, counts, _ = P.cover(400, [prod(1, "x", 500, 55), prod(2, "x", 1000, 95)])
        self.assertEqual((cost, counts), (5500, {1: 1}))

    def test_cover_respects_stock(self):
        cost, counts, _ = P.cover(1800, [prod(1, "x", 500, 55, stock=10), prod(2, "x", 1000, 95, stock=1)])
        self.assertEqual(counts, {2: 1, 1: 2})
        self.assertIsNone(P.cover(5000, [prod(1, "x", 500, 55, stock=2)]))

    def test_cover_is_optimal(self):
        rng = random.Random(3)
        for _ in range(300):
            packs = [prod(i, "x", rng.choice([100, 200, 250, 500, 1000]), rng.randint(10, 200)) for i in range(rng.randint(1, 3))]
            need = rng.randint(1, 2500)
            best = None  # brute force
            for a in range(0, 30):
                for b in range(0, 30 if len(packs) > 1 else 1):
                    for c in range(0, 30 if len(packs) > 2 else 1):
                        ks = [a, b, c][:len(packs)]
                        if sum(k * p["pack_size"] for k, p in zip(ks, packs)) >= need:
                            cost = sum(k * p["price_paise"] for k, p in zip(ks, packs))
                            best = cost if best is None else min(best, cost)
            self.assertEqual(P.cover(need, packs)[0], best)

    def test_build_cart_skips_staples(self):
        c = P.build_cart([DAL, SAMBAR], 4, PRODUCTS, ING, pantry_has_staples=True)
        self.assertNotIn("salt", {l["covers_ingredient"] for l in c["lines"]})
        dal = [l for l in c["lines"] if l["covers_ingredient"] == "toor_dal"]
        self.assertEqual(dal[0]["needed_qty"], 350)
        self.assertEqual(c["total_paise"], sum(l["line_total"] for l in c["lines"]))
        c2 = P.build_cart([DAL], 4, PRODUCTS, ING, pantry_has_staples=False)
        self.assertIn("salt", {l["covers_ingredient"] for l in c2["lines"]})

    def test_scaling(self):
        c = P.build_cart([PANEER], 6, PRODUCTS, ING, True)  # 200 g for 2 -> 600 g for 6
        self.assertEqual(sum(l["packs"] for l in c["lines"] if l["covers_ingredient"] == "paneer"), 3)


class BudgetTests(unittest.TestCase):
    TOPUPS = [prod(100 + i, "x", 1, r, "pcs", stock=20, topup=1, diet=d, name=f"top{i}")
              for i, (r, d) in enumerate([(10, "vegan"), (15, "veg"), (22, "vegan"), (27, "veg"), (35, "vegan"), (48, "egg"), (60, "veg"), (90, "vegan")])]

    def test_over_budget_gives_suggestions(self):
        sel = [DAL, SAMBAR, PANEER]
        cart = P.build_cart(sel, 6, PRODUCTS, ING, True)
        res = P.fit_to_budget(cart, cart["total_paise"] - 5000, PRODUCTS, "veg",
                              {"selected": sel, "people": 6, "ingredients": ING, "pantry": True})
        self.assertFalse(res["ok"])
        self.assertEqual(res["over_paise"], 5000)
        self.assertTrue(res["suggestions"])
        self.assertEqual(res["add"], [])
        self.assertIn("over", res["message"])

    def test_fill_lands_in_window(self):
        cart = P.build_cart([DAL], 4, PRODUCTS, ING, True)
        for budget in (cart["total_paise"] + 5000, cart["total_paise"] + 23000, cart["total_paise"] + 31000):
            res = P.fit_to_budget(cart, budget, PRODUCTS + self.TOPUPS, "veg")
            self.assertTrue(res["in_window"], res)
            self.assertTrue(budget - 3000 <= res["total_paise"] <= budget - 2000)
            self.assertTrue(all(next(p for p in self.TOPUPS if p["id"] == a["sku"])["diet"] in ("veg", "vegan") for a in res["add"]))

    def test_never_over_budget(self):
        rng = random.Random(9)
        for _ in range(1500):
            total = rng.randint(0, 200000)
            budget = total + rng.randint(-5000, 60000)
            tops = [prod(200 + i, "x", 1, rng.randint(5, 150), "pcs", stock=rng.randint(0, 5), topup=1, diet=rng.choice(["veg", "vegan", "egg"]))
                    for i in range(rng.randint(0, 10))]
            res = P.fit_to_budget({"total_paise": total, "lines": []}, budget, tops, rng.choice(["veg", "egg", "vegan", "nonveg"]))
            if total <= budget:
                self.assertTrue(res["ok"])
                self.assertLessEqual(res["total_paise"], budget)
                self.assertLessEqual(len([1 for a in res["add"] for _ in range(a["packs"])]), 6)
            else:
                self.assertFalse(res["ok"])

    def test_already_in_window(self):
        res = P.fit_to_budget({"total_paise": 147600, "lines": []}, 150000, self.TOPUPS, "veg")
        self.assertEqual(res["add"], [])
        self.assertTrue(res["in_window"])
        self.assertEqual(res["message"], "Your cart: ₹1,476, ₹24 under your ₹1,500 budget.")

    def test_coverage(self):
        c = P.coverage(4, 2, ["lunch", "dinner"], [DAL, SAMBAR, PANEER])
        self.assertEqual((c["slots_needed"], c["slots_chosen"], c["servings_needed"]), (4, 3, 16))


class RealDataTests(unittest.TestCase):
    """The checklist scenario on the real seed data: 4 people, Rs 1,500, 2 days, veg, high protein, stove + pressure cooker."""

    @classmethod
    def setUpClass(cls):
        import json
        d = Path(__file__).resolve().parent.parent / "app" / "data"
        cls.R = json.loads((d / "recipes.json").read_text(encoding="utf-8"))
        cls.I = {i["id"]: i for i in json.loads((d / "ingredients.json").read_text(encoding="utf-8"))}
        cls.PR = json.loads((d / "products_demo.json").read_text(encoding="utf-8"))

    def test_checklist_scenario(self):
        f = P.filter_recipes(self.R, "veg", ["gas_stove", "pressure_cooker"], ["lunch", "dinner"])
        self.assertGreaterEqual(len(f), 30)
        ranked = P.rank_recipes(f, self.I, "high_protein")
        for n in range(1, 9):  # whatever the shopper picks, the cart never exceeds the budget after fitting
            sel = [x["recipe"] for x in ranked[:n]]
            cart = P.build_cart(sel, 4, self.PR, self.I, True)
            self.assertEqual(cart["missing"], [])
            res = P.fit_to_budget(cart, 150000, self.PR, "veg", {"selected": sel, "people": 4, "ingredients": self.I, "pantry": True})
            if cart["total_paise"] <= 150000:
                self.assertLessEqual(res["total_paise"], 150000)
                if cart["total_paise"] >= 150000 - 50000:  # a gap that 6 top-ups can fill: must land Rs 20-30 under
                    self.assertTrue(res["in_window"], (n, cart["total_paise"], res))
            else:
                self.assertFalse(res["ok"])
                self.assertTrue(res["suggestions"])

    def test_every_ingredient_maps_to_a_product(self):
        mapped = {p["ingredient_id"] for p in self.PR}
        for r in self.R:
            for line in r["ingredients"]:
                self.assertIn(line["id"], self.I, r["id"])
                self.assertIn(line["id"], mapped, r["id"])

    def test_nutrition_is_computed_and_sane(self):
        for r in self.R:
            n = P.recipe_nutrition(r, self.I)
            self.assertTrue(0 <= n["kcal"] < 2500, (r["id"], n))
            self.assertTrue(0 <= n["protein_g"] < 150, (r["id"], n))


if __name__ == "__main__":
    unittest.main()
