
import tempfile
import unittest
import sqlite3
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import create_app

CODE = "4601234567893"


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app(Path(self.tmp.name) / "test.db")
        self.client = self.app.test_client()

    def move(self, kind, qty, key, barcode=CODE, client=None):
        return (client or self.client).post("/api/movements", json={
            "barcode": barcode, "kind": kind, "quantity": qty, "request_id": key,
        })

    def balance(self):
        return self.client.get("/api/products/" + CODE).json["stock"]

    def active(self):
        return [p for p in self.client.get("/api/purchases").json
                if p["barcode"] == CODE and p["status"] == "open"]

    def test_catalog_and_unknown_barcode(self):
        catalog = self.client.get("/api/products").json
        self.assertEqual(len(catalog), 9)
        self.assertEqual(self.client.get("/api/products/99999999").status_code, 404)

    def test_receipt_closes_initial_request(self):
        self.assertEqual(self.active()[0]["quantity"], 20)
        self.assertEqual(self.move("receipt", 10, "receipt-10").status_code, 201)
        self.assertEqual(self.balance(), 10)
        self.assertEqual(self.active(), [])

    def test_product_creation_and_duplicate_barcode(self):
        product = dict(barcode="12345678", name="Стойка", category="Комплектующие",
                       stock=2, minimum=4, target=10, price_kopecks=129900)
        created = self.client.post("/api/products", json=product)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/api/products", json=product).status_code, 409)
        self.assertEqual(self.client.get("/api/products/12345678").json["price_kopecks"], 129900)
        movements = self.client.get("/api/movements").json
        self.assertEqual([(m["kind"], m["quantity"]) for m in movements], [("receipt", 2)])
        purchases = self.client.get("/api/purchases").json
        self.assertEqual([p["quantity"] for p in purchases if p["barcode"] == "12345678"], [8])

    def test_legacy_database_keeps_stock_after_migration(self):
        db_path = Path(self.tmp.name) / "legacy.db"
        with closing(sqlite3.connect(db_path)) as db, db:
            db.executescript("""
                CREATE TABLE products(id INTEGER PRIMARY KEY, barcode TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
                                      stock INTEGER NOT NULL DEFAULT 0, minimum INTEGER NOT NULL, target INTEGER NOT NULL);
                INSERT INTO products VALUES(1,'4601234567893','Старый кабель',37,5,20);
            """)
        for _ in range(2):
            record = create_app(db_path).test_client().get("/api/products/" + CODE).json
            self.assertEqual((record["name"], record["stock"], record["price_kopecks"]),
                             ("Старый кабель", 37, 39000))

    def test_threshold_and_replenishment(self):
        self.move("receipt", 10, "threshold0")
        self.move("shipment", 5, "threshold1")
        self.assertEqual(self.active(), [])
        self.move("shipment", 1, "threshold2")
        request = self.active()[0]
        self.assertEqual(request["quantity"], 16)
        self.move("shipment", 1, "threshold3")
        self.assertEqual([(r["id"], r["quantity"]) for r in self.active()], [(request["id"], 17)])

    def test_insufficient_qty_changes_nothing(self):
        self.assertEqual(self.move("shipment", 1, "insuff-01").status_code, 409)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(len(self.client.get("/api/movements").json), 0)

    def test_retry_and_request_conflict(self):
        self.assertEqual(self.move("receipt", 6, "repeat-01").status_code, 201)
        self.assertEqual(self.move("receipt", 6, "repeat-01").status_code, 200)
        self.assertEqual(self.move("receipt", 7, "repeat-01").status_code, 409)
        self.assertEqual(self.balance(), 6)

    def test_invalid_quantities(self):
        for qty in [0, -1, True, "2", 2.5, 1000001]:
            with self.subTest(qty=qty):
                self.assertEqual(self.move("receipt", qty, "invalid-x").status_code, 400)
        self.assertEqual(self.balance(), 0)

    def test_parallel_shipments(self):
        self.move("receipt", 10, "parallel-0")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda i: self.move(
                "shipment", 7, f"parallel-{i}", client=self.app.test_client()).status_code, [1, 2]))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(self.balance(), 3)
        self.assertEqual(self.active()[0]["quantity"], 17)


if __name__ == "__main__":
    unittest.main()
