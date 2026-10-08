"""Data access for shared catalogues and warehouse inventory."""
from db import utc_now_iso


class EntityDAO:
    table = ''
    fields = ()

    def __init__(self, db):
        self.db = db

    def get_by_id(self, identifier):
        return self.db.query_one(f'SELECT * FROM {self.table} WHERE id=?', (identifier,))

    def list_all(self):
        return self.db.query_all(f'SELECT * FROM {self.table} ORDER BY name COLLATE NOCASE')

    def update(self, identifier, **fields):
        if not fields:
            return
        if not set(fields) <= set(self.fields):
            raise ValueError('Unsupported fields')
        if self.table in ('products', 'warehouses'):
            fields['updated_at'] = utc_now_iso()
        self.db.execute(f"UPDATE {self.table} SET " + ', '.join(f'{key}=?' for key in fields) + ' WHERE id=?', (*fields.values(), identifier))

    def delete(self, identifier):
        self.db.execute(f'DELETE FROM {self.table} WHERE id=?', (identifier,))


class ProductDAO(EntityDAO):
    table = 'products'
    fields = ('name', 'sku', 'description')

    def create(self, name, sku, description):
        now = utc_now_iso()
        return self.db.execute('INSERT INTO products(name,sku,description,created_at,updated_at) VALUES(?,?,?,?,?)', (name, sku, description, now, now))

    def get_by_name_or_sku(self, token):
        return self.db.query_one('SELECT * FROM products WHERE name=? OR sku=?', (token, token))

    def list_all(self, warehouse_id=None):
        if warehouse_id is None:
            return self.db.query_all('''SELECT p.*, COALESCE(SUM(s.quantity),0) AS quantity_in_stock,
                NULL AS reorder_level FROM products p LEFT JOIN warehouse_stock s ON s.product_id=p.id
                GROUP BY p.id ORDER BY p.name COLLATE NOCASE''')
        return self.db.query_all('''SELECT p.*, COALESCE(s.quantity,0) AS quantity_in_stock,
            COALESCE(s.reorder_level,0) AS reorder_level FROM products p
            LEFT JOIN warehouse_stock s ON s.product_id=p.id AND s.warehouse_id=?
            ORDER BY p.name COLLATE NOCASE''', (warehouse_id,))


class SupplierDAO(EntityDAO):
    table = 'suppliers'
    fields = ('name', 'contact_name', 'phone', 'email', 'address')

    def create(self, name, contact_name, phone, email, address):
        return self.db.execute('INSERT INTO suppliers(name,contact_name,phone,email,address,created_at) VALUES(?,?,?,?,?,?)', (name, contact_name, phone, email, address, utc_now_iso()))

    def get_by_name(self, name):
        return self.db.query_one('SELECT * FROM suppliers WHERE name=?', (name,))


class WarehouseDAO(EntityDAO):
    table = 'warehouses'
    fields = ('name', 'address')

    def create(self, name, address=None):
        now = utc_now_iso()
        return self.db.execute('INSERT INTO warehouses(name,address,created_at,updated_at) VALUES(?,?,?,?)', (name, address, now, now))


class SupplierProductDAO:
    def __init__(self, db):
        self.db = db

    def add(self, supplier_id, product_id, purchase_price):
        self.db.execute('INSERT INTO supplier_products(supplier_id,product_id,purchase_price) VALUES(?,?,?)', (supplier_id, product_id, purchase_price))

    def set_price(self, supplier_id, product_id, purchase_price):
        with self.db.transaction() as conn:
            cursor = conn.execute('UPDATE supplier_products SET purchase_price=? WHERE supplier_id=? AND product_id=?', (purchase_price, supplier_id, product_id))
            if cursor.rowcount != 1:
                raise ValueError('Product is not associated with this supplier')

    def remove(self, supplier_id, product_id):
        self.db.execute('DELETE FROM supplier_products WHERE supplier_id=? AND product_id=?', (supplier_id, product_id))

    def list_products(self, supplier_id):
        return self.db.query_all('''SELECT p.*, sp.purchase_price FROM products p JOIN supplier_products sp ON sp.product_id=p.id
            WHERE sp.supplier_id=? ORDER BY p.name COLLATE NOCASE''', (supplier_id,))


class StockDAO:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def adjust(conn, product_id, warehouse_id, delta):
        if delta < 0:
            cursor = conn.execute('''UPDATE warehouse_stock SET quantity=quantity+?
                WHERE product_id=? AND warehouse_id=? AND quantity>=?''', (delta, product_id, warehouse_id, -delta))
            if cursor.rowcount != 1:
                raise ValueError('Insufficient stock in the selected warehouse')
        else:
            conn.execute('''INSERT INTO warehouse_stock(product_id,warehouse_id,quantity) VALUES(?,?,?)
                ON CONFLICT(product_id,warehouse_id) DO UPDATE SET quantity=quantity+excluded.quantity''', (product_id, warehouse_id, delta))

    def set_reorder_level(self, product_id, warehouse_id, level):
        self.db.execute('''INSERT INTO warehouse_stock(product_id,warehouse_id,reorder_level) VALUES(?,?,?)
            ON CONFLICT(product_id,warehouse_id) DO UPDATE SET reorder_level=excluded.reorder_level''', (product_id, warehouse_id, level))

    def low_stock(self, warehouse_id=None):
        sql = '''SELECT p.id, p.name, p.sku, w.id AS warehouse_id, w.name AS warehouse_name,
            COALESCE(s.quantity,0) AS quantity_in_stock, COALESCE(s.reorder_level,0) AS reorder_level
            FROM products p CROSS JOIN warehouses w LEFT JOIN warehouse_stock s
            ON s.product_id=p.id AND s.warehouse_id=w.id
            WHERE COALESCE(s.quantity,0)<=COALESCE(s.reorder_level,0)'''
        params = ()
        if warehouse_id is not None:
            sql += ' AND w.id=?'
            params = (warehouse_id,)
        return self.db.query_all(sql + ' ORDER BY w.name COLLATE NOCASE,p.name COLLATE NOCASE', params)


class MovementDAO:
    table = ''
    date_field = ''

    def __init__(self, db):
        self.db = db

    def list_between(self, start_iso, end_iso, warehouse_id=None):
        sql = f'''SELECT m.*, p.name AS product_name, w.name AS warehouse_name FROM {self.table} m
            JOIN products p ON p.id=m.product_id JOIN warehouses w ON w.id=m.warehouse_id
            WHERE m.{self.date_field} BETWEEN ? AND ?'''
        if self.table == 'purchases':
            sql = sql.replace('m.*, p.name', 'm.*, sup.name AS supplier_name, p.name').replace('WHERE m.', 'JOIN suppliers sup ON sup.id=m.supplier_id WHERE m.', 1)
        params = [start_iso, end_iso]
        if warehouse_id is not None:
            sql += ' AND m.warehouse_id=?'
            params.append(warehouse_id)
        return self.db.query_all(sql + f' ORDER BY m.{self.date_field},m.id', params)

    def list_recent(self, limit=50):
        return self.db.query_all(f'''SELECT m.*,p.name AS product_name,w.name AS warehouse_name
            FROM {self.table} m JOIN products p ON p.id=m.product_id
            JOIN warehouses w ON w.id=m.warehouse_id ORDER BY m.{self.date_field} DESC,m.id DESC LIMIT ?''', (limit,))


class PurchaseDAO(MovementDAO):
    table = 'purchases'
    date_field = 'purchased_at'

    @staticmethod
    def create(conn, product_id, supplier_id, warehouse_id, quantity, unit_cost):
        return conn.execute('INSERT INTO purchases(product_id,supplier_id,warehouse_id,quantity,unit_cost,purchased_at) VALUES(?,?,?,?,?,?)', (product_id, supplier_id, warehouse_id, quantity, unit_cost, utc_now_iso())).lastrowid


class SaleDAO(MovementDAO):
    table = 'sales'
    date_field = 'sold_at'

    @staticmethod
    def create(conn, product_id, warehouse_id, quantity, unit_price, customer_name, notes):
        return conn.execute('INSERT INTO sales(product_id,warehouse_id,quantity,unit_price,sold_at,customer_name,notes) VALUES(?,?,?,?,?,?,?)', (product_id, warehouse_id, quantity, unit_price, utc_now_iso(), customer_name, notes)).lastrowid

    def sales_summary(self, warehouse_id=None):
        where = ' WHERE s.warehouse_id=?' if warehouse_id is not None else ''
        return self.db.query_all('''SELECT p.id AS product_id,p.name AS product_name,
            SUM(s.quantity) AS total_quantity_sold,SUM(s.quantity*s.unit_price) AS total_revenue
            FROM sales s JOIN products p ON p.id=s.product_id''' + where +
            ' GROUP BY p.id ORDER BY total_revenue DESC', (warehouse_id,) if warehouse_id is not None else ())


class TransferDAO:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def create(conn, product_id, source, destination, quantity, notes):
        return conn.execute('''INSERT INTO transfers(product_id,source_warehouse_id,destination_warehouse_id,
            quantity,transferred_at,notes) VALUES(?,?,?,?,?,?)''', (product_id, source, destination, quantity, utc_now_iso(), notes)).lastrowid

    def list_all(self, product_id=None, warehouse_id=None):
        sql = '''SELECT t.*,p.name AS product_name,a.name AS source_name,b.name AS destination_name
            FROM transfers t JOIN products p ON p.id=t.product_id
            JOIN warehouses a ON a.id=t.source_warehouse_id JOIN warehouses b ON b.id=t.destination_warehouse_id WHERE 1=1'''
        params = []
        if product_id is not None:
            sql += ' AND t.product_id=?'
            params.append(product_id)
        if warehouse_id is not None:
            sql += ' AND (t.source_warehouse_id=? OR t.destination_warehouse_id=?)'
            params.extend([warehouse_id, warehouse_id])
        return self.db.query_all(sql + ' ORDER BY t.transferred_at DESC,t.id DESC', params)
