
import os
import re
import sqlite3
from uuid import uuid4
from contextlib import closing
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
BARCODE = re.compile(r"[0-9]{8,14}")
MAX_QUANTITY = 1_000_000

DATABASE_SETUP = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    barcode TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
    minimum INTEGER NOT NULL CHECK(minimum >= 0),
    target INTEGER NOT NULL CHECK(target >= minimum),
    category TEXT NOT NULL DEFAULT 'Без категории',
    price_kopecks INTEGER CHECK(price_kopecks >= 0)
);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    kind TEXT NOT NULL CHECK(kind IN ('receipt', 'shipment')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    stock_after INTEGER NOT NULL CHECK(stock_after >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_requests (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_request
ON purchase_requests(product_id) WHERE status = 'open';

INSERT OR IGNORE INTO products(barcode,name,minimum,target) VALUES
('4601234567893','Кабель USB-C',5,20),
('4601234567800','Адаптер питания',3,12),
('4601234567817','Сетевой фильтр',2,10);

INSERT OR IGNORE INTO products(barcode,name,stock,minimum,target) VALUES
('4601234567909','Клавиатура',24,8,32),
('4601234567916','Мышь беспроводная',18,6,28),
('4601234567923','Кабель HDMI',32,10,45),
('4601234567930','USB-накопитель 64 ГБ',4,8,25),
('4601234567947','USB-концентратор',3,5,16),
('4601234567954','Переходник USB-C',12,5,20);

UPDATE products
SET category = CASE WHEN name LIKE 'Кабель%' THEN 'Кабели' ELSE 'Аксессуары' END,
    price_kopecks = CASE barcode
        WHEN '4601234567893' THEN 39000 WHEN '4601234567800' THEN 149000
        WHEN '4601234567817' THEN 99000 WHEN '4601234567909' THEN 249000
        WHEN '4601234567916' THEN 129000 WHEN '4601234567923' THEN 45000
        WHEN '4601234567930' THEN 89000 WHEN '4601234567947' THEN 159000
        WHEN '4601234567954' THEN 59000 END
WHERE price_kopecks IS NULL AND barcode IN (
    '4601234567893','4601234567800','4601234567817','4601234567909',
    '4601234567916','4601234567923','4601234567930','4601234567947','4601234567954'
);
"""


def replenish(db, product, balance):
    product_id = product["id"]
    if balance < product["minimum"]:
        db.execute(
            """INSERT INTO purchase_requests(product_id,quantity,status)
               VALUES(?,?,'open')
               ON CONFLICT(product_id) WHERE status='open'
               DO UPDATE SET quantity=excluded.quantity, updated_at=CURRENT_TIMESTAMP""",
            (product_id, product["target"] - balance),
        )
    else:
        db.execute(
            """UPDATE purchase_requests SET status='closed',updated_at=CURRENT_TIMESTAMP
               WHERE product_id=? AND status='open'""",
            (product_id,),
        )


def create_app(database=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16_384
    path = database or os.environ.get("WAREHOUSE_DB", str(ROOT / "warehouse.db"))

    def connect():
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(products)")}
        if columns and "category" not in columns:
            db.execute("ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT 'Без категории'")
        if columns and "price_kopecks" not in columns:
            db.execute("ALTER TABLE products ADD COLUMN price_kopecks INTEGER CHECK(price_kopecks >= 0)")
        db.executescript(DATABASE_SETUP)
        db.execute("BEGIN IMMEDIATE")
        for item in db.execute("SELECT * FROM products"):
            # Initial drafts correspond to the initial zero balances.
            if not db.execute("SELECT 1 FROM movements WHERE product_id=?", (item["id"],)).fetchone():
                replenish(db, item, item["stock"])

    def error(message, status):
        return jsonify(error=message), status

    @app.get("/")
    def overview():
        return send_from_directory(ROOT, "dashboard.html")

    @app.get("/inventory")
    def inventory():
        return send_from_directory(ROOT, "inventory.html")

    @app.get("/api")
    def api_documentation():
        return send_from_directory(ROOT, "api.html")

    @app.get("/api/products")
    def products():
        with closing(connect()) as db:
            return jsonify([dict(row) for row in db.execute("SELECT * FROM products ORDER BY id")])

    @app.get("/api/products/<barcode>")
    def product(barcode):
        with closing(connect()) as db:
            row = db.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
            return jsonify(dict(row)) if row else error("Товар не найден", 404)

    @app.post("/api/products")
    def add_product():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Ожидается объект JSON", 400)
        barcode, name, category = (data.get(key) for key in ("barcode", "name", "category"))
        stock, minimum, target, price = (data.get(key) for key in ("stock", "minimum", "target", "price_kopecks"))
        if (not isinstance(barcode, str) or not BARCODE.fullmatch(barcode)
                or not isinstance(name, str) or not 1 <= len(name.strip()) <= 100
                or not isinstance(category, str) or len(category.strip()) > 60
                or any(type(n) is not int or not 0 <= n <= MAX_QUANTITY for n in (stock, minimum, target))
                or target < minimum or type(price) is not int or not 0 <= price <= 100_000_000_00):
            return error("Проверьте поля товара, цену и пороги остатков", 400)
        with closing(connect()) as db, db:
            cursor = db.execute("""INSERT INTO products(barcode,name,category,stock,minimum,target,price_kopecks)
                                 VALUES(?,?,?,?,?,?,?) ON CONFLICT(barcode) DO NOTHING""",
                                (barcode, name.strip(), category.strip() or "Без категории", stock, minimum, target, price))
            if not cursor.rowcount:
                return error("Этот штрихкод уже есть в каталоге", 409)
            item = db.execute("SELECT * FROM products WHERE id=?", (cursor.lastrowid,)).fetchone()
            if stock > 0:
                db.execute("""INSERT INTO movements(request_id,product_id,kind,quantity,stock_after)
                            VALUES(?,?,'receipt',?,?)""", (uuid4().hex, item["id"], stock, stock))
            replenish(db, item, stock)
            return jsonify(dict(item)), 201

    @app.get("/api/movements")
    def movements():
        with closing(connect()) as db:
            rows = db.execute("""SELECT m.*,p.name,p.barcode FROM movements m
                                 JOIN products p ON p.id=m.product_id ORDER BY m.id DESC LIMIT 100""")
            return jsonify([dict(row) for row in rows])

    @app.get("/api/purchases")
    def purchases():
        with closing(connect()) as db:
            rows = db.execute("""SELECT r.*,p.name,p.barcode,p.stock,p.minimum,p.target
                                 FROM purchase_requests r JOIN products p ON p.id=r.product_id
                                 ORDER BY r.id DESC LIMIT 100""")
            return jsonify([dict(row) for row in rows])

    @app.post("/api/movements")
    def move():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Ожидается объект JSON", 400)
        barcode, kind, quantity, key = (data.get(field) for field in
                                        ("barcode", "kind", "quantity", "request_id"))
        if (not isinstance(barcode, str) or not BARCODE.fullmatch(barcode)
                or kind not in ("receipt", "shipment")
                or type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY
                or not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key)):
            return error("Проверьте штрихкод, вид операции, количество и идентификатор", 400)
        try:
            with closing(connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                item = db.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
                if item is None:
                    return error("Товар не найден", 404)
                previous = db.execute("SELECT * FROM movements WHERE request_id=?", (key,)).fetchone()
                if previous:
                    if (previous["product_id"], previous["kind"], previous["quantity"]) != (
                            item["id"], kind, quantity):
                        return error("Идентификатор уже использован для другой операции", 409)
                    return jsonify(dict(previous)), 200
                balance = item["stock"] + (quantity if kind == "receipt" else -quantity)
                if balance < 0:
                    return error("Недостаточный остаток", 409)
                db.execute("UPDATE products SET stock=? WHERE id=?", (balance, item["id"]))
                cursor = db.execute(
                    """INSERT INTO movements(request_id,product_id,kind,quantity,stock_after)
                       VALUES(?,?,?,?,?)""",
                    (key, item["id"], kind, quantity, balance),
                )
                replenish(db, item, balance)
                row = db.execute("SELECT * FROM movements WHERE id=?", (cursor.lastrowid,)).fetchone()
                return jsonify(dict(row)), 201
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                return error("Склад занят. Повторите операцию с тем же идентификатором", 503)
            raise

    return app


if __name__ == "__main__":
    create_app().run(host=os.environ.get("WAREHOUSE_HOST", "127.0.0.1"), port=8000)
