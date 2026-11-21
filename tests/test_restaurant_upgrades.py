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


if __name__ == "__main__":
    unittest.main()
