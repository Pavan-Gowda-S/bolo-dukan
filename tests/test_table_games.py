"""Bill Roulette, Housie and Lucky Spin: server-side randomness, checked claims, prizes added at ₹0."""
import json
import random
import time
import unittest

from app import tablegames
from tests.test_restaurant_upgrades import Base, call, config, dbm


class TicketTests(unittest.TestCase):
    def test_real_tambola_tickets(self):
        r = random.Random(7)
        for _ in range(500):
            g = tablegames.make_ticket(r)
            nums = tablegames.ticket_numbers(g)
            self.assertEqual(len(nums), 15)
            self.assertEqual(len(set(nums)), 15)
            self.assertTrue(all(sum(1 for n in line if n) == 5 for line in g))
            for c in range(9):
                col = [g[x][c] for x in range(3) if g[x][c]]
                self.assertTrue(1 <= len(col) <= 3)
                self.assertEqual(col, sorted(col))
                lo, hi = (1, 9) if c == 0 else (80, 90) if c == 8 else (10 * c, 10 * c + 9)
                self.assertTrue(all(lo <= n <= hi for n in col))

    def test_check_claim(self):
        g = tablegames.make_ticket(random.Random(1))
        first = [n for n in g[0] if n]
        self.assertTrue(tablegames.check_claim(g, set(first), "line"))
        self.assertFalse(tablegames.check_claim(g, set(first[:4]), "line"))
        self.assertFalse(tablegames.check_claim(g, set(first), "full"))
        self.assertTrue(tablegames.check_claim(g, set(tablegames.ticket_numbers(g)), "full"))


class GameRouteTests(Base):
    def setUp(self):
        super().setUp()
        self._g = (config.FEATURE_ROULETTE, config.FEATURE_HOUSIE, config.FEATURE_LUCKY_SPIN)
        config.FEATURE_ROULETTE = config.FEATURE_HOUSIE = config.FEATURE_LUCKY_SPIN = True

    def tearDown(self):
        config.FEATURE_ROULETTE, config.FEATURE_HOUSIE, config.FEATURE_LUCKY_SPIN = self._g
        super().tearDown()

    def test_roulette(self):
        sid, g = self.start(0)
        self.assertEqual(call("POST", f"/api/session/{sid}/roulette", {"players": ["Solo"]}, headers=g)[0], 400)
        r = call("POST", f"/api/session/{sid}/roulette", {"players": ["Anu", "Bala", "Chitra", "anu"]}, headers=g)[1]
        self.assertEqual(r["players"], ["Anu", "Bala", "Chitra"])   # duplicates removed
        self.assertNotIn("loser", r)                                  # never revealed before the end
        loser = None
        for _ in range(3):
            p = call("POST", f"/api/session/{sid}/roulette/{r['id']}/pull", {}, headers=g)[1]
            if p["last"]["bang"]:
                loser = p["loser"]
                break
        self.assertIsNotNone(loser)
        self.assertEqual(call("POST", f"/api/session/{sid}/roulette/{r['id']}/pull", {}, headers=g)[0], 409)
        self.assertEqual(call("GET", f"/api/session/{sid}", headers=g)[1]["bill_payer"], loser)

    def test_housie_claims_are_checked(self):
        sid, g = self.start(0)
        st = call("POST", f"/api/session/{sid}/housie/join", {}, headers=g)[1]
        self.assertEqual(len(tablegames.ticket_numbers(st["ticket"])), 15)
        self.assertEqual(call("POST", f"/api/session/{sid}/housie/claim", {"prize": "line"}, headers=g)[0], 409)  # nothing called yet
        line = [n for n in st["ticket"][0] if n]
        with dbm.db() as conn:  # make the server call this row's numbers first, and start the game in the past
            others = [n for n in range(1, 91) if n not in line]
            conn.execute("UPDATE housie_rounds SET seq = ?, starts_at = ? WHERE id = ?",
                         (json.dumps(line + others), time.time() - 5 * tablegames.HOUSIE_EVERY + 1, st["round"]))
        self.assertEqual(call("POST", f"/api/session/{sid}/housie/claim", {"prize": "full"}, headers=g)[0], 409)
        s, r, _ = call("POST", f"/api/session/{sid}/housie/claim", {"prize": "line"}, headers=g)
        self.assertEqual((s, r["won"]), (200, "First line"), r)
        self.assertEqual(call("POST", f"/api/session/{sid}/housie/claim", {"prize": "line"}, headers=g)[0], 409)  # once per game
        prizes = call("GET", "/api/dashboard", cookie=self.owner)[1]["game_prizes"]
        self.assertEqual([(p["game"], p["kind"]) for p in prizes], [("Housie", "juice")])

    def test_spin_unlock_and_prize_at_zero(self):
        sid, g = self.start(0)
        config.LUCKY_SPIN_MIN_PAISE = 15000
        self.assertEqual(call("POST", f"/api/session/{sid}/spin", {}, headers=g)[0], 409)  # nothing ordered yet
        oid = self.order(sid, g, ((0, 2),))[1]["order_id"]
        call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, self.owner)
        tablegames.rng.uniform = lambda a, b: 1  # land on segment 0: Free chai
        try:
            s, r, _ = call("POST", f"/api/session/{sid}/spin", {}, headers=g)
        finally:
            del tablegames.rng.uniform
        self.assertEqual((s, r["landed"], r["prize"]), (200, 0, "Free chai"), r)
        self.assertEqual(call("POST", f"/api/session/{sid}/spin", {}, headers=g)[0], 409)  # one spin per visit
        prize = call("GET", "/api/dashboard", cookie=self.owner)[1]["game_prizes"][0]
        s, r, _ = call("POST", f"/api/prizes/{prize['id']}/give", {}, self.owner)
        self.assertTrue(r["added"], r)
        v = call("GET", f"/api/session/{sid}", headers=g)[1]
        free = [i for o in v["orders"] for i in o["items"] if "prize, free" in i["name"]]
        self.assertEqual(len(free), 1)
        self.assertEqual(free[0]["unit_price_paise"], 0)
        self.assertEqual(v["bill_paise"], 16000)  # the free item doesn't change the bill
        self.assertEqual(call("POST", f"/api/prizes/{prize['id']}/give", {}, self.owner)[0], 409)

    def test_switches_off(self):
        sid, g = self.start(0)
        config.FEATURE_ROULETTE = config.FEATURE_HOUSIE = config.FEATURE_LUCKY_SPIN = False
        for path in ("roulette", "housie/join", "spin"):
            self.assertEqual(call("POST", f"/api/session/{sid}/{path}", {"players": ["a", "b"]}, headers=g)[0], 404)


if __name__ == "__main__":
    unittest.main()
