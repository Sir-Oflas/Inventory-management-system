"""Inventory rules. Every movement owns a single atomic database transaction."""
import math
from dao import (ProductDAO, SupplierDAO, WarehouseDAO, SupplierProductDAO,
                 StockDAO, PurchaseDAO, SaleDAO, TransferDAO)


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{label} must be an integer >= {minimum}')


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Price must be finite and non-negative')


def name_required(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Name is required')
    return name.strip()


class InventoryService:
    def __init__(self, db):
        self.db = db
        self.products = ProductDAO(db)
        self.suppliers = SupplierDAO(db)
        self.warehouses = WarehouseDAO(db)
        self.catalog = SupplierProductDAO(db)
        self.stock = StockDAO(db)
        self.purchases = PurchaseDAO(db)
        self.sales = SaleDAO(db)
        self.transfers = TransferDAO(db)

    def add_product(self, name, sku=None, description=None):
        return self.products.create(name_required(name), sku, description)

    def update_product(self, product_id, **fields):
        if 'name' in fields:
            fields['name'] = name_required(fields['name'])
        self.products.update(product_id, **fields)

    def delete_product(self, product_id):
        self.products.delete(product_id)

    def list_products(self, warehouse_id=None):
        if warehouse_id is not None:
            self._require(self.warehouses, warehouse_id, 'Warehouse')
        return self.products.list_all(warehouse_id)

    def get_product(self, product_id):
        return self.products.get_by_id(product_id)

    def add_supplier(self, name, contact_name=None, phone=None, email=None, address=None):
        return self.suppliers.create(name_required(name), contact_name, phone, email, address)

    def update_supplier(self, supplier_id, **fields):
        if 'name' in fields:
            fields['name'] = name_required(fields['name'])
        self.suppliers.update(supplier_id, **fields)

    def delete_supplier(self, supplier_id):
        self.suppliers.delete(supplier_id)

    def list_suppliers(self):
        return self.suppliers.list_all()

    def get_supplier(self, supplier_id):
        return self.suppliers.get_by_id(supplier_id)

    def add_warehouse(self, name, address=None):
        return self.warehouses.create(name_required(name), address)

    def update_warehouse(self, warehouse_id, **fields):
        self._require(self.warehouses, warehouse_id, 'Warehouse')
        if 'name' in fields:
            fields['name'] = name_required(fields['name'])
        self.warehouses.update(warehouse_id, **fields)

    def delete_warehouse(self, warehouse_id):
        self.warehouses.delete(warehouse_id)

    def list_warehouses(self):
        return self.warehouses.list_all()

    def get_warehouse(self, warehouse_id):
        return self.warehouses.get_by_id(warehouse_id)

    @staticmethod
    def _require(dao, identifier, label):
        if dao.get_by_id(identifier) is None:
            raise ValueError(f'{label} not found')

    def associate_supplier_product(self, supplier_id, product_id, purchase_price=0):
        money(purchase_price)
        self._require(self.suppliers, supplier_id, 'Supplier')
        self._require(self.products, product_id, 'Product')
        self.catalog.add(supplier_id, product_id, purchase_price)

    def set_supplier_price(self, supplier_id, product_id, purchase_price):
        money(purchase_price)
        self.catalog.set_price(supplier_id, product_id, purchase_price)

    def create_supplier_product(self, supplier_id, name, sku, description, purchase_price):
        money(purchase_price)
        name = name_required(name)
        with self.db.transaction() as conn:
            if conn.execute('SELECT 1 FROM suppliers WHERE id=?', (supplier_id,)).fetchone() is None:
                raise ValueError('Supplier not found')
            from db import utc_now_iso
            now = utc_now_iso()
            product_id = conn.execute('INSERT INTO products(name,sku,description,created_at,updated_at) VALUES(?,?,?,?,?)', (name, sku, description, now, now)).lastrowid
            conn.execute('INSERT INTO supplier_products VALUES(?,?,?)', (supplier_id, product_id, purchase_price))
            return product_id

    def list_product_catalogue(self):
        return self.db.query_all('SELECT * FROM products ORDER BY name COLLATE NOCASE')

    def list_warehouse_products(self, warehouse_id):
        self._require(self.warehouses, warehouse_id, 'Warehouse')
        return self.db.query_all('''SELECT p.*,s.quantity AS quantity_in_stock,s.reorder_level
            FROM warehouse_stock s JOIN products p ON p.id=s.product_id
            WHERE s.warehouse_id=? ORDER BY p.name COLLATE NOCASE''', (warehouse_id,))

    def remove_supplier_product(self, supplier_id, product_id):
        self.catalog.remove(supplier_id, product_id)

    def list_supplier_products(self, supplier_id):
        return self.catalog.list_products(supplier_id)

    def set_reorder_level(self, product_id, warehouse_id, level):
        integer(level, 'Reorder level')
        self._require(self.products, product_id, 'Product')
        self._require(self.warehouses, warehouse_id, 'Warehouse')
        self.stock.set_reorder_level(product_id, warehouse_id, level)

    def get_stock(self, product_id, warehouse_id):
        self._require(self.products, product_id, 'Product')
        self._require(self.warehouses, warehouse_id, 'Warehouse')
        row = self.db.query_one('SELECT quantity FROM warehouse_stock WHERE product_id=? AND warehouse_id=?', (product_id, warehouse_id))
        return row['quantity'] if row else 0

    def list_available_products(self, warehouse_id):
        return [p for p in self.list_products(warehouse_id) if p['quantity_in_stock'] > 0]

    @staticmethod
    def _movement_entities(conn, product_id, *warehouses):
        if conn.execute('SELECT 1 FROM products WHERE id=?', (product_id,)).fetchone() is None:
            raise ValueError('Product not found')
        for warehouse_id in warehouses:
            if conn.execute('SELECT 1 FROM warehouses WHERE id=?', (warehouse_id,)).fetchone() is None:
                raise ValueError('Warehouse not found')

    def record_purchase(self, product_id, quantity, unit_cost, supplier_id, warehouse_id):
        integer(quantity, 'Quantity', 1)
        money(unit_cost)
        with self.db.transaction() as conn:
            self._movement_entities(conn, product_id, warehouse_id)
            if conn.execute('SELECT 1 FROM supplier_products WHERE supplier_id=? AND product_id=?', (supplier_id, product_id)).fetchone() is None:
                raise ValueError('Product is not in the selected supplier catalogue')
            self.stock.adjust(conn, product_id, warehouse_id, quantity)
            return self.purchases.create(conn, product_id, supplier_id, warehouse_id, quantity, unit_cost)

    def record_sale(self, product_id, quantity, unit_price, warehouse_id, customer_name=None, notes=None):
        integer(quantity, 'Quantity', 1)
        money(unit_price)
        with self.db.transaction() as conn:
            self._movement_entities(conn, product_id, warehouse_id)
            self.stock.adjust(conn, product_id, warehouse_id, -quantity)
            return self.sales.create(conn, product_id, warehouse_id, quantity, unit_price, customer_name, notes)

    def record_transfer(self, product_id, source_warehouse_id, destination_warehouse_id, quantity, notes=None):
        integer(quantity, 'Quantity', 1)
        if source_warehouse_id == destination_warehouse_id:
            raise ValueError('Source and destination must be different')
        with self.db.transaction() as conn:
            self._movement_entities(conn, product_id, source_warehouse_id, destination_warehouse_id)
            self.stock.adjust(conn, product_id, source_warehouse_id, -quantity)
            self.stock.adjust(conn, product_id, destination_warehouse_id, quantity)
            return self.transfers.create(conn, product_id, source_warehouse_id, destination_warehouse_id, quantity, notes)

    def list_transfers(self, product_id=None, warehouse_id=None):
        return self.transfers.list_all(product_id, warehouse_id)

    def report_stock_levels(self, warehouse_id=None):
        return self.list_products(warehouse_id)

    def report_low_stock(self, warehouse_id=None):
        return self.stock.low_stock(warehouse_id)

    def report_sales_summary(self, warehouse_id=None):
        return self.sales.sales_summary(warehouse_id)

    def report_sales_between(self, start_iso, end_iso, warehouse_id=None):
        return self.sales.list_between(start_iso, end_iso, warehouse_id)

    def report_purchases_between(self, start_iso, end_iso, warehouse_id=None):
        return self.purchases.list_between(start_iso, end_iso, warehouse_id)
