
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
BARCODE = re.compile(r"[0-9]{8,14}")
MAX_QUANTITY = 1_000_000


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
        db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
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
