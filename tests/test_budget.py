"""Run:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.budget import build_budget_basket, kind_of  # noqa: E402


def item(i, name, cat, rupees, available=1):
    return {"id": i, "name": name, "category": cat, "price_paise": rupees * 100, "available": available, "name_local": ""}


MENU = [
    item(1, "Masala Dosa", "Dosa", 90),
    item(2, "Ghee Roast Dosa", "Dosa", 130),
    item(3, "South Indian Meals", "Rice & Meals", 150),
    item(4, "Filter Coffee", "Beverages", 40),
    item(5, "Sweet Lassi", "Beverages", 60),
    item(6, "Gulab Jamun", "Desserts", 50),
    item(7, "Idli Vada", "Breakfast", 60),
    item(8, "Masala Puri", "Snacks", 60),
    item(9, "Tomato Soup", "Starters", 70),
]


class KindTests(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(kind_of("Beverages"), "drink")
        self.assertEqual(kind_of("Desserts"), "dessert")
        self.assertEqual(kind_of("Rice & Meals"), "main")
        self.assertEqual(kind_of("Dosa"), "main")
        self.assertEqual(kind_of("Breakfast"), "breakfast")
        self.assertEqual(kind_of("Snacks"), "snack")
        self.assertEqual(kind_of("Menu", "Filter Coffee"), "drink")  # falls back to the dish name


class BudgetTests(unittest.TestCase):
    def test_budget_fits_exactly(self):
        # 2 people, Rs 400: meals 300 -> left 100 -> lassi 2x60=120 too much, coffee 2x40=80 -> left 20
        r = build_budget_basket(MENU, 40000, 2, "dinner")
        self.assertTrue(r["ok"])
        self.assertEqual([(l["name"], l["qty"]) for l in r["proposed_items"]], [("South Indian Meals", 2), ("Filter Coffee", 2)])
        self.assertEqual(r["total_paise"], 38000)
        self.assertEqual(r["remaining_paise"], 2000)

        exact = build_budget_basket([item(1, "Thali", "Meals", 200), item(2, "Tea", "Beverages", 50)], 50000, 2, "lunch")
        self.assertEqual(exact["total_paise"], 50000)
        self.assertEqual(exact["remaining_paise"], 0)
        self.assertIsNone(exact["suggestion"])

    def test_leftover_gives_one_suggestion_not_added(self):
        r = build_budget_basket(MENU, 70000, 4, "dinner")
        # 4 x 150 = 600, left 100 -> no drink/dessert/starter fits for all 4 -> suggest 2 Gulab Jamun = 100
        self.assertEqual([l["name"] for l in r["proposed_items"]], ["South Indian Meals"])
        self.assertEqual(r["remaining_paise"], 10000)
        self.assertIsNotNone(r["suggestion"])
        self.assertEqual((r["suggestion"]["name"], r["suggestion"]["qty"]), ("Gulab Jamun", 2))
        self.assertEqual(r["total_paise"], 60000)  # the suggestion is NOT added to the total
        self.assertLessEqual(r["suggestion"]["line_total_paise"], r["remaining_paise"])
        self.assertNotIn(r["suggestion"]["menu_item_id"], [l["menu_item_id"] for l in r["proposed_items"]])
        self.assertIn("left", r["suggestion"]["text"])

    def test_budget_too_low(self):
        r = build_budget_basket(MENU, 20000, 4, "dinner")
        self.assertFalse(r["ok"])
        self.assertEqual(r["min_budget_paise"], 4 * 9000)  # cheapest main x people
        self.assertEqual(r["proposed_items"], [])
        self.assertIn("starts at", r["reply_text"])

    def test_unavailable_items_are_skipped(self):
        menu = [dict(m) for m in MENU]
        for m in menu:
            if m["name"] in ("South Indian Meals", "Filter Coffee"):
                m["available"] = 0
        r = build_budget_basket(menu, 80000, 4, "dinner")
        names = [l["name"] for l in r["proposed_items"]]
        self.assertNotIn("South Indian Meals", names)
        self.assertNotIn("Filter Coffee", names)
        self.assertEqual(names[0], "Ghee Roast Dosa")

    def test_breakfast_and_snacks(self):
        self.assertEqual(build_budget_basket(MENU, 20000, 2, "breakfast")["proposed_items"][0]["name"], "Idli Vada")
        self.assertEqual(build_budget_basket(MENU, 20000, 2, "snacks")["proposed_items"][0]["name"], "Masala Puri")

    def test_total_never_exceeds_budget(self):
        rng = random.Random(7)
        for _ in range(2000):
            menu = [item(i, f"Dish {i}", rng.choice(["Meals", "Dosa", "Beverages", "Desserts", "Starters", "Snacks", "Breakfast"]),
                         rng.randint(10, 400), rng.choice([1, 1, 1, 0])) for i in range(1, rng.randint(2, 25))]
            budget = rng.randint(1, 3000) * 100
            r = build_budget_basket(menu, budget, rng.randint(1, 10), rng.choice([None, "dinner", "lunch", "breakfast", "snacks"]))
            self.assertLessEqual(r["total_paise"], budget)
            self.assertEqual(r["total_paise"], sum(l["line_total_paise"] for l in r["proposed_items"]))
            if r["suggestion"]:
                self.assertLessEqual(r["suggestion"]["line_total_paise"], r["remaining_paise"])

    def test_bad_input(self):
        self.assertFalse(build_budget_basket(MENU, 0, 2)["ok"])
        self.assertFalse(build_budget_basket(MENU, 10000, 0)["ok"])


if __name__ == "__main__":
    unittest.main()
