"""Restaurant upgrades: menu preview, seats, dish details, kitchen TV, staff, game rooms, floor plan.

Runs the real routes against a temporary database (no network: Cashfree and AI are not called).
    python -m pytest -q
"""
import json
import tempfile
import unittest
import uuid
from email.message import Message
from pathlib import Path

from app import config

config.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
import app.db as dbm  # noqa: E402

dbm.DB_PATH = config.DB_PATH
from app import main  # noqa: E402
from app.web import HTTPError, Request  # noqa: E402

FLAGS = ("FEATURE_MENU_PREVIEW", "FEATURE_SEATS", "FEATURE_DISH_DETAILS", "FEATURE_KITCHEN_TV", "FEATURE_STAFF",
         "FEATURE_GAME_ROOMS", "FEATURE_FLOOR_PLAN", "FEATURE_KANNADA_ALERTS", "FEATURE_BUDGET_ORDER")


def call(method, path, body=None, cookie="", headers=None, raw=None, ctype=None):
    m = Message()
    for k, v in (headers or {}).items():
        m[k] = v
    if cookie:
        m["Cookie"] = cookie
    if ctype:
        m["Content-Type"] = ctype
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    try:
        r = main.app.dispatch(Request(method, path, m, data, "127.0.0.1"))
        return r.status, (json.loads(r.body) if "json" in r.content_type else r.body), r
    except HTTPError as e:
        return e.status, {"detail": e.detail}, None


def multipart(fields=None, files=None):
    b = uuid.uuid4().hex
    out = b""
    for k, v in (fields or {}).items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, ct, d) in (files or {}).items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\nContent-Type: {ct}\r\n\r\n'.encode() + d + b"\r\n"
    return out + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def cookie_of(resp, name):
    for c in resp.cookies:
        if c.startswith(name + "="):
            return c.split(";", 1)[0]
    return ""


class Base(unittest.TestCase):
    """A fresh restaurant with 3 tables and a 3-dish menu for each test."""

    @classmethod
    def setUpClass(cls):
        dbm.init_db()

    def setUp(self):
        self._saved = {f: getattr(config, f) for f in FLAGS}
        for f in FLAGS:
            setattr(config, f, True)
        email = f"o{uuid.uuid4().hex[:8]}@x.co"
        s, r, resp = call("POST", "/api/owner/signup", {"email": email, "password": "secret1", "restaurant_name": "R " + email[:6]})
        self.assertEqual(s, 200, r)
        self.owner = cookie_of(resp, "bd_owner")
        s, r, _ = call("POST", "/api/owner/setup", {"table_count": 3, "language": "kn-IN"}, self.owner)
        self.assertEqual(s, 200, r)
        for name, local, price in (("Masala Dosa", "ಮಸಾಲೆ ದೋಸೆ", 8000), ("Filter Coffee", "ಫಿಲ್ಟರ್ ಕಾಫಿ", 3000), ("Idli Vada", "", 6000)):
            s, r, _ = call("POST", "/api/owner/menu", {"name": name, "name_local": local, "category": "Tiffin", "price_paise": price}, self.owner)
            self.assertEqual(s, 200, r)
        self.menu = call("GET", "/api/owner/menu", cookie=self.owner)[1]["items"]
        self.tables = call("GET", "/api/owner/qr", cookie=self.owner)[1]["tables"]

    def tearDown(self):
        for f, v in self._saved.items():
            setattr(config, f, v)

    def start(self, table=0, approve=True):
        tok = self.tables[table]["token"]
        s, r, _ = call("POST", f"/api/t/{tok}/start", {"device_id": uuid.uuid4().hex})
        self.assertEqual(s, 200, r)
        g = {"X-Guest-Token": r["guest_token"]}
        if approve:
            self.assertEqual(call("POST", f"/api/session/{r['session_id']}/approve", {}, self.owner)[0], 200)
        return r["session_id"], g

    def order(self, sid, g, items=((0, 2),)):
        return call("POST", f"/api/session/{sid}/orders", {"items": [{"menu_item_id": self.menu[i]["id"], "qty": q} for i, q in items]}, headers=g)


class MenuPreviewTests(Base):
    def test_menu_visible_before_start(self):
        s, r, _ = call("GET", f"/api/t/{self.tables[0]['token']}")
        self.assertEqual(s, 200)
        self.assertEqual(len(r["menu"]), 3)
        self.assertTrue(r["features"]["menu_preview"])

    def test_cannot_order_while_waiting(self):
        sid, g = self.start(approve=False)
        s, r, _ = self.order(sid, g)
        self.assertEqual(s, 409)
        self.assertEqual(r["detail"], main.WAIT_MSG)
        s, r, _ = call("POST", f"/api/session/{sid}/budget", {"budget_rupees": 500, "people": 2}, headers=g)
        self.assertEqual(s, 409)
        self.assertEqual(r["detail"], main.WAIT_MSG)

    def test_can_order_after_approval(self):
        sid, g = self.start(approve=False)
        self.assertEqual(call("POST", f"/api/session/{sid}/approve", {}, self.owner)[0], 200)
        s, r, _ = self.order(sid, g)
        self.assertEqual(s, 200, r)


class SeatsTests(Base):
    def test_default_four_and_save(self):
        me = call("GET", "/api/owner/me", cookie=self.owner)[1]
        self.assertEqual(me["seats"], [4, 4, 4])
        s, r, _ = call("POST", "/api/owner/setup", {"table_count": 3, "language": "kn-IN", "seats": [2, 6, 8]}, self.owner)
        self.assertEqual(s, 200, r)
        self.assertEqual(call("GET", "/api/owner/me", cookie=self.owner)[1]["seats"], [2, 6, 8])
        self.assertEqual([t["seats"] for t in call("GET", "/api/owner/qr", cookie=self.owner)[1]["tables"]], [2, 6, 8])
        self.assertEqual(call("GET", f"/api/t/{self.tables[1]['token']}")[1]["table"]["seats"], 6)
        dash = call("GET", "/api/dashboard", cookie=self.owner)[1]
        self.assertEqual([t["seats"] for t in dash["tables"]], [2, 6, 8])

    def test_validation(self):
        for bad in ([4, 4], [0, 4, 4], [4, 21, 4], ["x", 4, 4]):
            s, r, _ = call("POST", "/api/owner/setup", {"table_count": 3, "language": "kn-IN", "seats": bad}, self.owner)
            self.assertEqual(s, 400, (bad, r))

    def test_more_tables_keep_seats(self):
        call("POST", "/api/owner/setup", {"table_count": 3, "language": "kn-IN", "seats": [2, 6, 8]}, self.owner)
        call("POST", "/api/owner/setup", {"table_count": 4, "language": "kn-IN"}, self.owner)
        self.assertEqual(call("GET", "/api/owner/me", cookie=self.owner)[1]["seats"], [2, 6, 8, 4])


class DishDetailsTests(Base):
    def test_owner_values_shown_and_partial_update_keeps_them(self):
        dosa = self.menu[0]
        body = dict(dosa, description="Crisp dosa", is_veg="1", spice="2", allergens="dairy", kcal="350", protein_g="8.5",
                    carbs_g="", fat_g="12", fibre_g="")
        s, r, _ = call("PUT", f"/api/owner/menu/{dosa['id']}", body, self.owner)
        self.assertEqual(s, 200, r)
        # the old edit form (no detail keys) must not wipe them
        s, r, _ = call("PUT", f"/api/owner/menu/{dosa['id']}", {"name": "Masala Dosa", "price_paise": 8000, "category": "Tiffin"}, self.owner)
        self.assertEqual(s, 200, r)
        m = next(i for i in call("GET", f"/api/t/{self.tables[0]['token']}")[1]["menu"] if i["id"] == dosa["id"])
        self.assertEqual((m["description"], m["is_veg"], m["spice"], m["allergens"]), ("Crisp dosa", 1, 2, "dairy"))
        self.assertEqual(m["nutrition"], {"kcal": 350, "protein_g": 8.5, "carbs_g": None, "fat_g": 12.0, "fibre_g": None})
        self.assertEqual(m["nutrition_source"], "owner")

    def test_no_guessing(self):
        coffee = next(i for i in call("GET", f"/api/t/{self.tables[0]['token']}")[1]["menu"] if i["name"] == "Idli Vada")
        if not config.FEATURE_NUTRITION:
            self.assertNotIn("nutrition", coffee)

    def test_validation(self):
        dosa = self.menu[0]
        for bad in ({"spice": 5}, {"kcal": -3}, {"is_veg": "maybe"}, {"protein_g": "lots"}):
            s, r, _ = call("PUT", f"/api/owner/menu/{dosa['id']}", dict(dosa, **bad), self.owner)
            self.assertEqual(s, 400, (bad, r))

    def test_csv_optional_columns(self):
        data = b"name,price,category,is_veg,spice,kcal,protein_g,allergens\nPaneer Tikka,180,Starters,veg,2,320,18,dairy\nOdd,90,X,maybe,9,,,\n"
        raw, ct = multipart(files={"file": ("m.csv", "text/csv", data)})
        s, r, _ = call("POST", "/api/owner/menu/csv", cookie=self.owner, raw=raw, ctype=ct)
        self.assertEqual((s, r.get("added")), (200, 2), r)
        items = {i["name"]: i for i in call("GET", "/api/owner/menu", cookie=self.owner)[1]["items"]}
        self.assertEqual((items["Paneer Tikka"]["kcal"], items["Paneer Tikka"]["is_veg"], items["Paneer Tikka"]["allergens"]), (320, 1, "dairy"))
        self.assertIsNone(items["Odd"]["is_veg"])  # bad optional values are dropped, the dish is kept

    def test_flag_off_hides_details(self):
        config.FEATURE_DISH_DETAILS = False
        m = call("GET", f"/api/t/{self.tables[0]['token']}")[1]["menu"][0]
        self.assertNotIn("description", m)


class KitchenTests(Base):
    def setUp(self):
        super().setUp()
        from app import ai
        self._tts = ai.tts
        ai.tts = lambda text, lang: b"RIFF0000WAVE"

    def tearDown(self):
        from app import ai
        ai.tts = self._tts
        super().tearDown()

    def kitchen(self):
        url = call("GET", "/api/owner/kitchen-link", cookie=self.owner)[1]["url"]
        return url.rsplit("/", 1)[1]

    def test_board_flow(self):
        tok = self.kitchen()
        self.assertGreaterEqual(len(tok), 24)
        sid, g = self.start(1)
        oid = self.order(sid, g, ((0, 2), (1, 1)))[1]["order_id"]
        self.assertEqual(call("GET", f"/api/kitchen/{tok}/board")[1]["tickets"], [])  # pending: not in the kitchen yet
        self.assertEqual(call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, self.owner)[0], 200)
        b = call("GET", f"/api/kitchen/{tok}/board")[1]
        t = b["tickets"][0]
        self.assertEqual((t["table_number"], t["seats"], t["order_no"], t["status"]), (2, 4, 1, "ACCEPTED"))
        self.assertEqual([(i["qty"], i["name"], i["name_local"]) for i in t["items"]], [(2, "Masala Dosa", "ಮಸಾಲೆ ದೋಸೆ"), (1, "Filter Coffee", "ಫಿಲ್ಟರ್ ಕಾಫಿ")])
        text = json.dumps(b, ensure_ascii=False)
        for secret in ("price", "phone", "total", "8000"):
            self.assertNotIn(secret, text)
        # spoken once on the kitchen TV, never on the cashier dashboard
        a = b["announcements"][0]
        self.assertIn("ಟೇಬಲ್ 2", a["text_kn"])
        dash = call("GET", "/api/dashboard", cookie=self.owner)[1]
        self.assertFalse(any(x["event_type"] == "kitchen_order" for x in dash["announcements"]))
        c1 = call("POST", f"/api/kitchen/{tok}/announcements/{a['id']}/claim", {})[1]
        c2 = call("POST", f"/api/kitchen/{tok}/announcements/{a['id']}/claim", {})[1]
        self.assertTrue(c1["spoken_here"] and c1["audio"])
        self.assertFalse(c2["spoken_here"])
        self.assertEqual(call("GET", f"/api/kitchen/{tok}/board")[1]["announcements"], [])
        # preparing shows, served disappears
        call("POST", f"/api/orders/{oid}/status", {"status": "PREPARING"}, self.owner)
        self.assertEqual(call("GET", f"/api/kitchen/{tok}/board")[1]["tickets"][0]["status"], "PREPARING")
        call("POST", f"/api/orders/{oid}/status", {"status": "SERVED"}, self.owner)
        self.assertEqual(call("GET", f"/api/kitchen/{tok}/board")[1]["tickets"], [])

    def test_regenerate_invalidates(self):
        old = self.kitchen()
        new = call("POST", "/api/owner/kitchen-link/regenerate", {}, self.owner)[1]["url"].rsplit("/", 1)[1]
        self.assertNotEqual(old, new)
        self.assertEqual(call("GET", f"/api/kitchen/{old}/board")[0], 404)
        self.assertEqual(call("GET", f"/api/kitchen/{new}/board")[0], 200)
        self.assertEqual(call("GET", "/api/kitchen/short/board")[0], 404)

    def test_flag_off(self):
        tok = self.kitchen()
        config.FEATURE_KITCHEN_TV = False
        self.assertEqual(call("GET", f"/api/kitchen/{tok}/board")[0], 404)
        self.assertEqual(call("GET", f"/kitchen/{tok}")[0], 404)


class StaffTests(Base):
    def add_waiter(self, username="ravi", pin="1234", tables=None, cookie=None):
        body = {"name": username.title(), "username": username, "pin": pin}
        if tables is not None:
            body["table_ids"] = tables
        s, r, _ = call("POST", "/api/owner/staff", body, cookie or self.owner)
        self.assertEqual(s, 200, r)
        slug = call("GET", "/api/owner/me", cookie=cookie or self.owner)[1]["restaurant"]["slug"]
        s, r, resp = call("POST", "/api/staff/login", {"restaurant": slug, "username": username, "pin": pin})
        self.assertEqual(s, 200, r)
        return cookie_of(resp, "bd_staff")

    def test_waiter_flow_and_audit(self):
        w = self.add_waiter(tables=[self.tables[0]["id"]])
        sid, g = self.start(0, approve=False)
        self.assertEqual(call("POST", f"/api/session/{sid}/approve", {}, w)[0], 200)
        oid = self.order(sid, g)[1]["order_id"]
        board = call("GET", "/api/waiter/board", cookie=w)[1]
        self.assertEqual([t["number"] for t in board["tables"]], [1])
        self.assertNotIn("price", json.dumps(board))
        self.assertEqual(call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, w)[0], 200)
        self.assertEqual(call("POST", f"/api/orders/{oid}/status", {"status": "SERVED"}, w)[0], 200)
        dash = call("GET", "/api/dashboard", cookie=self.owner)[1]
        t1 = dash["tables"][0]["session"]
        self.assertEqual(t1["approved_by"], "waiter:Ravi")
        self.assertEqual(t1["orders"][0]["accepted_by"], "waiter:Ravi")

    def test_waiter_blocked_from_owner_routes(self):
        w = self.add_waiter()
        for method, path in (("GET", "/api/dashboard"), ("GET", "/api/owner/menu"), ("GET", "/api/dashboard/summary"),
                             ("GET", "/api/owner/qr"), ("GET", "/api/owner/staff"), ("POST", "/api/owner/setup")):
            s, _, _ = call(method, path, {} if method == "POST" else None, w)
            self.assertIn(s, (401, 403), path)
        sid, g = self.start(0)
        self.assertIn(call("POST", f"/api/session/{sid}/cash", {}, w)[0], (401, 403))
        self.assertIn(call("POST", f"/api/session/{sid}/free", {}, w)[0], (401, 403))

    def test_unassigned_and_other_restaurant_403(self):
        w = self.add_waiter(tables=[self.tables[0]["id"]])
        sid, g = self.start(2, approve=False)  # table 3: not assigned
        self.assertEqual(call("POST", f"/api/session/{sid}/approve", {}, w)[0], 403)
        self.assertEqual(call("POST", f"/api/session/{sid}/approve", {}, self.owner)[0], 200)  # owner still can
        oid = self.order(sid, g)[1]["order_id"]
        self.assertEqual(call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, w)[0], 403)
        other = Base.setUp  # a second restaurant
        o2 = self.owner
        other(self)
        w2 = self.add_waiter("asha", "5678")
        self.owner = o2
        self.assertEqual(call("POST", f"/api/orders/{oid}/status", {"status": "ACCEPTED"}, w2)[0], 403)

    def test_wrong_pin_rate_limited(self):
        self.add_waiter("kiran", "4321")
        slug = call("GET", "/api/owner/me", cookie=self.owner)[1]["restaurant"]["slug"]
        codes = [call("POST", "/api/staff/login", {"restaurant": slug, "username": "kiran", "pin": "0000"})[0] for _ in range(6)]
        self.assertEqual(codes[:4], [403] * 4)
        self.assertEqual(codes[5], 429)
        self.assertEqual(call("POST", "/api/staff/login", {"restaurant": slug, "username": "kiran", "pin": "4321"})[0], 429)

    def test_owner_cookie_is_not_a_staff_cookie(self):
        forged = "bd_staff=" + self.owner.split("=", 1)[1]
        self.assertEqual(call("GET", "/api/waiter/board", cookie=forged)[0], 401)

    def test_flag_off(self):
        w = self.add_waiter()
        config.FEATURE_STAFF = False
        self.assertEqual(call("GET", "/api/waiter/board", cookie=w)[0], 404)
        sid, g = self.start(0, approve=False)
        self.assertEqual(call("POST", f"/api/session/{sid}/approve", {}, w)[0], 401)


if __name__ == "__main__":
    unittest.main()
