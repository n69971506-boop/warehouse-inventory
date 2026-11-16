
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    barcode TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
    minimum INTEGER NOT NULL CHECK(minimum >= 0),
    target INTEGER NOT NULL CHECK(target >= minimum)
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
