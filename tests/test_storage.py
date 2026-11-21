"""Restaurant storage room finder: owner-only list, starter list, quantities, low stock, other restaurants kept out."""
import uuid

from tests.test_restaurant_upgrades import Base, call, config, cookie_of


class StorageTests(Base):
    def setUp(self):
        super().setUp()
        self._sf = config.FEATURE_STORAGE_FINDER
        config.FEATURE_STORAGE_FINDER = True

    def tearDown(self):
        config.FEATURE_STORAGE_FINDER = self._sf
        super().tearDown()

    def test_first_visit_is_full_list(self):
        r = call("GET", "/api/owner/storage", cookie=self.owner)[1]
        self.assertGreater(len(r["items"]), 150)
        self.assertIn("Vegetables", r["categories"])
        it = next(i for i in r["items"] if i["name"] == "Milk")
        self.assertTrue(it["note"])
        call("POST", f"/api/owner/storage/{it['id']}/delete", {}, self.owner)
        r2 = call("GET", "/api/owner/storage", cookie=self.owner)[1]  # not refilled behind the owner's back
        self.assertEqual(len(r2["items"]), len(r["items"]) - 1)

    def _empty(self):
        for i in call("GET", "/api/owner/storage", cookie=self.owner)[1]["items"]:
            call("POST", f"/api/owner/storage/{i['id']}/delete", {}, self.owner)

    def test_add_find_update_delete(self):
        self._empty()
        s, r, _ = call("POST", "/api/owner/storage", {"name": " Parcel  covers ", "category": "Covers", "qty": 50, "unit": "pcs", "low_at": 20}, self.owner)
        self.assertEqual(s, 200, r)
        it = r["items"][0]
        self.assertEqual((it["name"], it["low"]), ("Parcel covers", False))
        self.assertEqual(call("POST", "/api/owner/storage", {"name": "parcel COVERS", "category": "X"}, self.owner)[0], 409)
        self.assertEqual(call("POST", "/api/owner/storage", {"name": "", "category": "X"}, self.owner)[0], 400)
        self.assertEqual(call("POST", "/api/owner/storage", {"name": "A", "category": "X", "qty": -1}, self.owner)[0], 400)
        s, r, _ = call("POST", f"/api/owner/storage/{it['id']}", {"qty": 10}, self.owner)
        self.assertEqual((r["items"][0]["qty"], r["items"][0]["low"], r["low"]), (10, True, 1))
        s, r, _ = call("POST", f"/api/owner/storage/{it['id']}/delete", {}, self.owner)
        self.assertEqual(r["items"], [])

    def test_starter_list_once(self):
        self._empty()
        r = call("POST", "/api/owner/storage/starter", {}, self.owner)[1]
        n = len(r["items"])
        self.assertGreater(n, 150)
        self.assertIn("Vegetables", r["categories"])
        self.assertIn("Covers & packaging", r["categories"])
        self.assertEqual(len(call("POST", "/api/owner/storage/starter", {}, self.owner)[1]["items"]), n)

    def test_private_and_switch(self):
        self._empty()
        it = call("POST", "/api/owner/storage", {"name": "Ladle", "category": "Utensils"}, self.owner)[1]["items"][0]
        self.assertEqual(call("GET", "/api/owner/storage")[0], 401)
        email = f"o{uuid.uuid4().hex[:8]}@x.co"
        other = cookie_of(call("POST", "/api/owner/signup", {"email": email, "password": "secret1", "restaurant_name": "Other"})[2], "bd_owner")
        theirs = call("GET", "/api/owner/storage", cookie=other)[1]["items"]
        self.assertNotIn(it["id"], [i["id"] for i in theirs])
        self.assertEqual(call("POST", f"/api/owner/storage/{it['id']}", {"qty": 5}, other)[0], 404)
        self.assertEqual(call("POST", f"/api/owner/storage/{it['id']}/delete", {}, other)[0], 404)
        config.FEATURE_STORAGE_FINDER = False
        self.assertEqual(call("GET", "/api/owner/storage", cookie=self.owner)[0], 404)
        self.assertEqual(call("GET", "/owner/storage")[0], 404)
