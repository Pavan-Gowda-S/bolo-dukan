import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.split import split_by_items, split_equal  # noqa: E402
from app.summary import summarize  # noqa: E402


class SplitTests(unittest.TestCase):
    def test_equal_exact(self):
        self.assertEqual(split_equal(1000, 3), [334, 333, 333])
        self.assertEqual(split_equal(90000, 3), [30000, 30000, 30000])
        self.assertEqual(split_equal(1, 3), [1, 0, 0])

    def test_equal_always_sums(self):
        rng = random.Random(1)
        for _ in range(5000):
            total, n = rng.randint(0, 10_000_000), rng.randint(1, 20)
            parts = split_equal(total, n)
            self.assertEqual(sum(parts), total)
            self.assertEqual(len(parts), n)
            self.assertLessEqual(max(parts) - min(parts), 1)
            self.assertEqual(parts, sorted(parts, reverse=True))  # extra paise on the first shares

    def test_equal_bad(self):
        with self.assertRaises(ValueError):
            split_equal(100, 0)

    def test_by_items(self):
        lines = [{"id": 1, "payer": "a", "amount_paise": 9000}, {"id": 2, "payer": "b", "amount_paise": 4000},
                 {"id": 3, "payer": "a", "amount_paise": 3000}, {"id": 4, "payer": None, "amount_paise": 1001}]
        out = split_by_items(lines, ["a", "b", "c"], shared_line_ids=[3])
        # shared: line 3 (3000) + unknown payer line 4 (1001) = 4001 -> 1334, 1334, 1333
        self.assertEqual(out, {"a": 9000 + 1334, "b": 4000 + 1334, "c": 1333})
        self.assertEqual(sum(out.values()), 17001)

    def test_by_items_always_sums(self):
        rng = random.Random(2)
        for _ in range(2000):
            payers = list(range(rng.randint(1, 6)))
            lines = [{"id": i, "payer": rng.choice(payers + [None, 99]), "amount_paise": rng.randint(0, 50000)}
                     for i in range(rng.randint(0, 15))]
            shared = [l["id"] for l in lines if rng.random() < 0.3]
            out = split_by_items(lines, payers, shared)
            self.assertEqual(sum(out.values()), sum(l["amount_paise"] for l in lines))
            self.assertTrue(all(v >= 0 for v in out.values()))


class SummaryTests(unittest.TestCase):
    def test_totals_match_paid_bills(self):
        bills = [{"session_id": 1, "table": 2, "amount_paise": 22000, "method": "online", "link_id": "x", "settled_at": "2026-11-21T05:00:00"},
                 {"session_id": 2, "table": 5, "amount_paise": 13050, "method": "cash", "link_id": None, "settled_at": "2026-11-21T04:00:00"},
                 {"session_id": 3, "table": 1, "amount_paise": 9000, "method": "split", "link_id": "y", "settled_at": "2026-11-21T06:00:00"}]
        items = [{"name": "Masala Dosa", "qty": 3, "unit_price_paise": 9000}, {"name": "Filter Coffee", "qty": 4, "unit_price_paise": 4000},
                 {"name": "Masala Dosa", "qty": 1, "unit_price_paise": 9000}, {"name": "Masala Chai (quiz prize, free)", "qty": 5, "unit_price_paise": 0},
                 {"name": "Idli", "qty": 2, "unit_price_paise": 4000}, {"name": "Vada", "qty": 1, "unit_price_paise": 5000}]
        s = summarize(bills, items)
        self.assertEqual(s["collected_paise"], 22000 + 13050 + 9000)
        self.assertEqual(s["collected_paise"], sum(b["amount_paise"] for b in bills))
        self.assertEqual(s["online_paise"] + s["cash_paise"], s["collected_paise"])
        self.assertEqual(s["bills"], 3)
        self.assertEqual(s["average_paise"], 44050 // 3)
        self.assertEqual([t["name"] for t in s["top_items"]], ["Filter Coffee", "Masala Dosa", "Idli"])
        self.assertEqual([b["session_id"] for b in s["bill_list"]], [2, 1, 3])

    def test_empty_day(self):
        s = summarize([], [])
        self.assertEqual((s["collected_paise"], s["bills"], s["average_paise"], s["top_items"]), (0, 0, 0, []))


if __name__ == "__main__":
    unittest.main()
