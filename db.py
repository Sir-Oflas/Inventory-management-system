import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
import sys


def _get_app_dir():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path=None):
        self.db_path = str(db_path if db_path is not None else _get_app_dir() / 'inventory.db')

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        conn = self._connect()
        try:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    sku TEXT UNIQUE, description TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    contact_name TEXT, phone TEXT, email TEXT, address TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS warehouses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT COLLATE NOCASE NOT NULL UNIQUE,
                    address TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS warehouse_stock (
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK(typeof(quantity) = 'integer' AND quantity >= 0),
                    reorder_level INTEGER NOT NULL DEFAULT 0 CHECK(typeof(reorder_level) = 'integer' AND reorder_level >= 0),
                    PRIMARY KEY(product_id, warehouse_id));
                CREATE TABLE IF NOT EXISTS supplier_products (
                    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    purchase_price REAL NOT NULL DEFAULT 0 CHECK(purchase_price >= 0),
                    PRIMARY KEY(supplier_id, product_id));
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
                    quantity INTEGER NOT NULL CHECK(typeof(quantity) = 'integer' AND quantity > 0),
                    unit_cost REAL NOT NULL CHECK(unit_cost >= 0), purchased_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
                    quantity INTEGER NOT NULL CHECK(typeof(quantity) = 'integer' AND quantity > 0),
                    unit_price REAL NOT NULL CHECK(unit_price >= 0), sold_at TEXT NOT NULL,
                    customer_name TEXT, notes TEXT);
                CREATE TABLE IF NOT EXISTS transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                    source_warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
                    destination_warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
                    quantity INTEGER NOT NULL CHECK(typeof(quantity) = 'integer' AND quantity > 0),
                    transferred_at TEXT NOT NULL, notes TEXT,
                    CHECK(source_warehouse_id != destination_warehouse_id));
                CREATE INDEX IF NOT EXISTS stock_warehouse ON warehouse_stock(warehouse_id);
                CREATE INDEX IF NOT EXISTS catalog_product ON supplier_products(product_id);
                CREATE INDEX IF NOT EXISTS purchases_product ON purchases(product_id);
                CREATE INDEX IF NOT EXISTS sales_product ON sales(product_id);
                CREATE INDEX IF NOT EXISTS transfers_product ON transfers(product_id);
                CREATE TRIGGER IF NOT EXISTS protect_product_stock BEFORE DELETE ON products
                    WHEN EXISTS(SELECT 1 FROM warehouse_stock WHERE product_id=OLD.id AND quantity>0)
                    BEGIN SELECT RAISE(ABORT, 'Product has positive stock'); END;
                CREATE TRIGGER IF NOT EXISTS protect_warehouse_stock BEFORE DELETE ON warehouses
                    WHEN EXISTS(SELECT 1 FROM warehouse_stock WHERE warehouse_id=OLD.id AND quantity>0)
                    BEGIN SELECT RAISE(ABORT, 'Warehouse has positive stock'); END;
            ''')
        finally:
            conn.close()

    def execute(self, sql, params=()):
        with self.transaction() as conn:
            return conn.execute(sql, params).lastrowid

    def query_all(self, sql, params=()):
        conn = self._connect()
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def query_one(self, sql, params=()):
        rows = self.query_all(sql, params)
        return rows[0] if rows else None
