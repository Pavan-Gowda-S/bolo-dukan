"""Blueprint reading (pure clean-up), tips and the Relay.app AI agent hook."""
import json
import unittest

from app import floorplan
from tests.test_restaurant_upgrades import Base, call, config  # same temporary database and helpers


class NormalizeLayoutTests(unittest.TestCase):
    def test_boxes_to_percent_and_filters(self):
        raw = {"tables": [[{"box_2d": [600, 80, 700, 140], "label": "T1", "seats": 4},
                           {"box_2d": [300, 60, 340, 95], "label": "T1", "seats": 4}],     # a stove burner, inside the range
                          [{"box_2d": [601, 81, 701, 141], "label": "T1", "seats": 4},       # same table from run 2
                           {"box_2d": [800, 460, 890, 590], "label": "T6", "seats": 99}]],   # silly chair count
               "rooms": [{"box_2d": [180, 37, 520, 347], "label": "kitchen"}, {"box_2d": [180, 37, 520, 347], "label": "kitchen"}],
               "counters": [{"box_2d": [250, 50, 500, 100], "label": "DOSA TAWA RANGE"}, {"box_2d": [1, 2, 3], "label": "bad"},
                            {"box_2d": [540, 800, 720, 950], "label": "CASHIER"}]}
        lay = floorplan.normalize_layout(raw)
        self.assertEqual([(t["label"], t["x"], t["y"]) for t in lay["tables"]], [("T1", 11.0, 65.0), ("T6", 52.5, 84.5)])
        self.assertIsNone(lay["tables"][1]["seats"])
        self.assertEqual([(r["type"], r["label"]) for r in lay["rooms"]], [("kitchen", "Kitchen")])
        self.assertEqual([c["kind"] for c in lay["counters"]], ["kitchen", "cashier"])

    def test_garbage_is_dropped_not_guessed(self):
        lay = floorplan.normalize_layout({"tables": [{"box_2d": "x"}, {"box_2d": [5, 5, 6, 6]}], "rooms": "nope", "counters": None})
        self.assertEqual(lay, {"rooms": [], "counters": [], "tables": [], "walls": []})
        self.assertEqual(floorplan.normalize_layout("junk")["tables"], [])

    def test_clean_saved_layout_clamps(self):
        out = floorplan.clean_saved_layout({"walls": [[0, 0, 150, 0, 9], [1, 2, "x", 4]], "rooms": [{"x": 1, "y": 2, "w": 30, "h": 20, "type": "evil", "label": "<b>K</b>"}],
                                            "counters": [{"x": -5, "y": 1, "w": 2, "h": 2, "kind": "cashier"}], "extra": 1})
        self.assertEqual(out["walls"], [[0.0, 0.0, 100.0, 0.0, 5.0]])
        self.assertEqual(out["rooms"][0]["type"], "other")
        self.assertEqual(out["counters"][0]["x"], 0.0)
        self.assertNotIn("extra", out)


class LayoutSaveTests(Base):
    def test_apply_layout_positions_and_seats(self):
        t1, t2 = self.tables[0]["id"], self.tables[1]["id"]
        body = {"layout": {"walls": [[3, 5, 90, 5, 1]], "rooms": [{"x": 3, "y": 20, "w": 30, "h": 30, "type": "kitchen", "label": "Kitchen"}],
                           "counters": [{"x": 80, "y": 54, "w": 15, "h": 18, "kind": "cashier", "label": "Cashier"}]},
                "positions": [{"table_id": t1, "x": 10.6, "y": 65}], "seats": {str(t2): 6}}
        s, r, _ = call("PUT", "/api/owner/floor/layout", body, self.owner)
        self.assertEqual(s, 200, r)
        f = call("GET", "/api/owner/floor", cookie=self.owner)[1]
        self.assertEqual(f["layout"]["counters"][0]["kind"], "cashier")
        self.assertEqual((f["tables"][0]["pos_x"], f["tables"][1]["seats"]), (10.6, 6))
        bad = dict(body, positions=[{"table_id": t1, "x": 300, "y": 1}])
        self.assertEqual(call("PUT", "/api/owner/floor/layout", bad, self.owner)[0], 400)

    def test_read_needs_blueprint_and_switch(self):
        config.FEATURE_FLOOR_AI, config.GEMINI_API_KEY = True, config.GEMINI_API_KEY or "test-key"
        self.assertEqual(call("POST", "/api/owner/floor/read", {}, self.owner)[0], 409)
        config.FEATURE_FLOOR_AI = False
        self.assertEqual(call("POST", "/api/owner/floor/read", {}, self.owner)[0], 404)


class TipTests(Base):
    def setUp(self):
        super().setUp()
        from app import cashfree
        self._saved_cf = (config.CASHFREE_APP_ID, config.CASHFREE_SECRET_KEY, cashfree.create_link)
        config.CASHFREE_APP_ID, config.CASHFREE_SECRET_KEY, config.FEATURE_TIPS = "x", "y", True
        self.links = []
        cashfree.create_link = lambda link_id, amount, *a, **k: (self.links.append(amount), {"link_url": "https://pay.test/" + link_id})[1]

    def tearDown(self):
        from app import cashfree
        config.CASHFREE_APP_ID, config.CASHFREE_SECRET_KEY, cashfree.create_link = self._saved_cf
        config.FEATURE_TIPS = False
        super().tearDown()

    def billed(self, table=0):
        sid, g = self.start(table)
        oid = self.order(sid, g, ((0, 2), (1, 1)))[1]["order_id"]  # 2 x 80 + 1 x 30 = 190
        call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, self.owner)
        call("POST", f"/api/session/{sid}/request-bill", {}, headers=g)
        return sid, g

    def test_percent_and_custom_tip_go_into_the_upi_amount(self):
        sid, g = self.billed()
        s, r, _ = call("POST", f"/api/session/{sid}/tip", {"percent": 10}, headers=g)
        self.assertEqual((s, r["tip_paise"], r["total_paise"]), (200, 1900, 20900))
        self.assertEqual(call("GET", f"/api/session/{sid}", headers=g)[1]["tip_paise"], 1900)
        self.assertEqual(call("POST", f"/api/session/{sid}/pay", {"phone": "9876543210"}, headers=g)[1]["amount_paise"], 20900)
        self.assertEqual(call("POST", f"/api/session/{sid}/tip", {"rupees": 50}, headers=g)[1]["tip_paise"], 5000)
        self.assertEqual(call("POST", f"/api/session/{sid}/pay", {"phone": "9876543210"}, headers=g)[1]["amount_paise"], 24000)
        self.assertEqual(self.links, [20900, 24000])  # a new link when the tip changes

    def test_tip_rules(self):
        sid, g = self.start(0)
        self.assertEqual(call("POST", f"/api/session/{sid}/tip", {"percent": 10}, headers=g)[0], 409)  # bill not ready
        sid, g = self.billed(1)
        for bad in ({"percent": 12}, {"rupees": -5}, {"rupees": 96}, {"rupees": "lots"}):  # 96 > half of 190
            self.assertEqual(call("POST", f"/api/session/{sid}/tip", bad, headers=g)[0], 400, bad)
        self.assertEqual(call("POST", f"/api/session/{sid}/tip", {"percent": 5})[0], 401)  # needs the guest token
        config.FEATURE_TIPS = False
        self.assertEqual(call("POST", f"/api/session/{sid}/tip", {"percent": 5}, headers=g)[0], 404)


class RelayTests(Base):
    def setUp(self):
        super().setUp()
        from app import relay
        self.sent = []
        self._rsaved = (config.FEATURE_RELAY, config.RELAY_WEBHOOK_URL, relay.request, relay.threading.Thread)
        config.FEATURE_RELAY, config.RELAY_WEBHOOK_URL = True, "https://hook.relay.app/api/v1/playbook/test/trigger/abc"
        relay.request = lambda method, url, body, headers, timeout: (self.sent.append((url, body)), (200, {}))[1]

        class NowThread:  # run "background" sends at once so the test can see them
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()
        relay.threading.Thread = NowThread

    def tearDown(self):
        from app import relay
        config.FEATURE_RELAY, config.RELAY_WEBHOOK_URL, relay.request, relay.threading.Thread = self._rsaved
        super().tearDown()

    def test_events_have_no_phone_numbers(self):
        sid, g = self.start(0)
        call("POST", f"/api/session/{sid}/call-waiter", {"reason": "Water"}, headers=g)
        oid = self.order(sid, g)[1]["order_id"]
        call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, self.owner)
        call("POST", f"/api/session/{sid}/request-bill", {}, headers=g)
        self.assertEqual(call("POST", f"/api/session/{sid}/cash", {}, self.owner)[0], 200)
        events = [b["event"] for _, b in self.sent]
        self.assertEqual(events, ["waiter_call", "bill_paid"])
        paid = self.sent[1][1]["data"]
        self.assertEqual((paid["table"], paid["method"], paid["amount_rupees"]), (1, "cash", 160.0))
        self.assertEqual(paid["items"][0]["name"], "Masala Dosa")
        s, r, _ = call("POST", "/api/owner/report/relay", {}, self.owner)
        self.assertEqual(s, 200, r)
        self.assertEqual(self.sent[-1][1]["event"], "daily_report")
        self.assertEqual(self.sent[-1][1]["data"]["collected_rupees"], 160.0)
        self.assertNotIn("98765", json.dumps([b for _, b in self.sent]))

    def test_off_sends_nothing(self):
        config.FEATURE_RELAY = False
        sid, g = self.start(0)
        call("POST", f"/api/session/{sid}/call-waiter", {"reason": "Water"}, headers=g)
        self.assertEqual(self.sent, [])
        self.assertEqual(call("POST", "/api/owner/report/relay", {}, self.owner)[0], 409)


if __name__ == "__main__":
    unittest.main()
