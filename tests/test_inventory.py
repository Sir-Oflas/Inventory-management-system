import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from db import Database
from services import InventoryService


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name)/'test.db')
        self.db.init_db()
        self.service = InventoryService(self.db)
        s = self.service
        self.product = s.add_product('Widget', 'W', None)
        self.other = s.add_product('Other', 'O', None)
        self.supplier = s.add_supplier('Supplier')
        self.supplier2 = s.add_supplier('Supplier 2')
        s.associate_supplier_product(self.supplier, self.product)
        self.a = s.add_warehouse('North')
        self.b = s.add_warehouse('South')

    def buy(self, amount=10, warehouse=None):
        return self.service.record_purchase(self.product, amount, 2, self.supplier, warehouse or self.a)

    def test_prices_belong_to_supplier_and_history_is_unchanged(self):
        s = self.service
        s.set_supplier_price(self.supplier, self.product, 3)
        s.associate_supplier_product(self.supplier2, self.product, 8)
        self.assertEqual(s.list_supplier_products(self.supplier)[0]['purchase_price'], 3)
        self.assertEqual(s.list_supplier_products(self.supplier2)[0]['purchase_price'], 8)
        self.assertNotIn('unit_price', s.get_product(self.product))
        self.buy()
        s.set_supplier_price(self.supplier, self.product, 5)
        self.assertEqual(self.db.query_all('SELECT unit_cost FROM purchases')[0]['unit_cost'], 2)
        for price in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                s.set_supplier_price(self.supplier, self.product, price)
        new = s.create_supplier_product(self.supplier, 'New', 'N', 'Description', 9)
        self.assertIn(new, [row['id'] for row in s.list_supplier_products(self.supplier)])
        self.assertEqual(s.list_warehouse_products(self.b), [])
        s.set_reorder_level(self.product, self.b, 4)
        self.assertEqual(len(s.list_warehouse_products(self.b)), 1)
        self.assertEqual(s.list_product_catalogue()[0]['name'], 'New')

    def test_catalogue_many_to_many_and_unlink_preserves_history(self):
        s = self.service
        s.associate_supplier_product(self.supplier2, self.product)
        self.assertEqual(len(s.list_supplier_products(self.supplier)), 1)
        self.assertEqual(s.list_supplier_products(self.supplier2)[0]['id'], self.product)
        self.buy()
        s.remove_supplier_product(self.supplier, self.product)
        self.assertEqual(s.list_supplier_products(self.supplier), [])
        self.assertEqual(len(s.list_supplier_products(self.supplier2)), 1)
        self.assertEqual(s.get_stock(self.product, self.a), 10)
        self.assertEqual(len(self.db.query_all('SELECT * FROM purchases')), 1)
        with self.assertRaises(ValueError):
            self.buy()

    def test_purchase_adds_stock_and_preserves_local_threshold(self):
        s = self.service
        s.set_reorder_level(self.product, self.a, 7)
        self.buy(10)
        self.buy(3)
        self.assertEqual(s.get_stock(self.product, self.a), 13)
        self.assertEqual(s.get_stock(self.product, self.b), 0)
        self.assertEqual(s.list_products(self.a)[1]['reorder_level'], 7)
        self.assertEqual(s.list_products()[1]['quantity_in_stock'], 13)
        self.assertIsNone(s.list_products()[1]['reorder_level'])

    def test_transfer_adds_existing_stock_preserves_threshold_and_total(self):
        s = self.service
        self.buy(10)
        self.buy(2, self.b)
        s.set_reorder_level(self.product, self.b, 8)
        s.record_transfer(self.product, self.a, self.b, 4, 'Move')
        self.assertEqual(s.get_stock(self.product, self.a), 6)
        self.assertEqual(s.get_stock(self.product, self.b), 6)
        self.assertEqual(s.list_products(self.b)[1]['reorder_level'], 8)
        self.assertEqual(s.list_products()[1]['quantity_in_stock'], 12)
        history = s.list_transfers(self.product, self.b)
        self.assertEqual(history[0]['notes'], 'Move')
        self.assertEqual(history[0]['source_name'], 'North')
        self.assertEqual(s.report_sales_summary(), [])
        self.assertEqual(len(self.db.query_all('SELECT * FROM purchases')), 2)

    def test_transfer_creates_destination_with_zero_threshold(self):
        self.buy()
        self.service.record_transfer(self.product, self.a, self.b, 10)
        self.assertEqual(self.service.get_stock(self.product, self.a), 0)
        self.assertEqual(self.service.get_stock(self.product, self.b), 10)
        self.assertEqual(self.service.list_products(self.b)[1]['reorder_level'], 0)
        self.assertEqual(self.service.list_available_products(self.a), [])

    def test_sale_uses_only_local_stock(self):
        self.buy()
        with self.assertRaises(ValueError):
            self.service.record_sale(self.product, 1, 4, self.b)
        self.assertEqual(self.db.query_all('SELECT * FROM sales'), [])
        self.service.record_sale(self.product, 3, 4, self.a)
        self.assertEqual(self.service.get_stock(self.product, self.a), 7)
        self.assertEqual(self.service.report_sales_summary(self.a)[0]['total_revenue'], 12)
        self.assertEqual(self.service.report_sales_summary(self.b), [])
        self.assertEqual(len(self.service.report_sales_between('2000', '9999', self.a)), 1)

    def test_invalid_quantities_and_references_leave_no_changes(self):
        self.buy()
        for quantity in (0, -1, 1.5, 1.0, True, '2'):
            for call in (
                lambda: self.service.record_purchase(self.product, quantity, 1, self.supplier, self.a),
                lambda: self.service.record_sale(self.product, quantity, 1, self.a),
                lambda: self.service.record_transfer(self.product, self.a, self.b, quantity),
            ):
                with self.assertRaises(ValueError):
                    call()
        for args in [(self.product, self.a, self.a, 1), (self.product, self.a, self.b, 11),
                     (999, self.a, self.b, 1), (self.product, self.a, 999, 1)]:
            with self.assertRaises(ValueError):
                self.service.record_transfer(*args)
        self.assertEqual(self.service.get_stock(self.product, self.a), 10)
        self.assertEqual(self.service.get_stock(self.product, self.b), 0)
        self.assertEqual(self.service.list_transfers(), [])
        for price in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.service.record_purchase(self.product, 1, price, self.supplier, self.a)

    def test_rollback_after_partial_updates_for_all_movements(self):
        self.buy()
        for dao, operation in [
            (self.service.purchases, lambda: self.buy(3, self.b)),
            (self.service.sales, lambda: self.service.record_sale(self.product, 2, 4, self.a)),
            (self.service.transfers, lambda: self.service.record_transfer(self.product, self.a, self.b, 2)),
        ]:
            with patch.object(dao, 'create', side_effect=RuntimeError('Injected failure')):
                with self.assertRaises(RuntimeError):
                    operation()
            self.assertEqual(self.service.get_stock(self.product, self.a), 10)
            self.assertEqual(self.service.get_stock(self.product, self.b), 0)
        self.assertEqual(self.service.list_transfers(), [])
        self.assertEqual(len(self.db.query_all('SELECT * FROM purchases')), 1)
        self.assertEqual(self.db.query_all('SELECT * FROM sales'), [])

    def test_independent_thresholds_and_zero_defaults(self):
        s = self.service
        self.buy(5)
        self.buy(5, self.b)
        s.set_reorder_level(self.product, self.a, 5)
        s.set_reorder_level(self.product, self.b, 4)
        alerts = s.report_low_stock()
        widget_alerts = [r for r in alerts if r['id'] == self.product]
        self.assertEqual([r['warehouse_id'] for r in widget_alerts], [self.a])
        self.assertEqual(len([r for r in alerts if r['id'] == self.other]), 2)
        for level in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                s.set_reorder_level(self.product, self.a, level)

    def test_protected_deletions_and_clean_config_removal(self):
        s = self.service
        self.buy()
        for action in (lambda: s.delete_warehouse(self.a), lambda: s.delete_product(self.product),
                       lambda: s.delete_supplier(self.supplier)):
            with self.assertRaises(sqlite3.IntegrityError):
                action()
        s.record_sale(self.product, 10, 4, self.a)
        with self.assertRaises(sqlite3.IntegrityError):
            s.delete_warehouse(self.a)
        s.set_reorder_level(self.other, self.b, 4)
        s.delete_warehouse(self.b)
        self.assertEqual(self.db.query_all('SELECT * FROM warehouse_stock WHERE warehouse_id=?', (self.b,)), [])
        s.associate_supplier_product(self.supplier2, self.other)
        s.delete_supplier(self.supplier2)
        self.assertEqual(s.list_supplier_products(self.supplier2), [])
        s.delete_product(self.other)

    def test_concurrent_sales_cannot_overdraw(self):
        from concurrent.futures import ThreadPoolExecutor
        self.buy(10)
        def sell():
            try:
                self.service.record_sale(self.product, 7, 4, self.a)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: sell(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.service.get_stock(self.product, self.a), 3)
        self.assertEqual(len(self.db.query_all('SELECT * FROM sales')), 1)

    def test_database_constraints_and_case_insensitive_warehouse_names(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.add_warehouse('nOrTh')
        for sql, params in [
            ('INSERT INTO warehouse_stock VALUES(?,?,?,?)', (self.product, self.a, -1, 0)),
            ('INSERT INTO warehouse_stock VALUES(?,?,?,?)', (self.product, self.a, 1.5, 0)),
            ('INSERT INTO warehouse_stock VALUES(?,?,?,?)', (self.product, 999, 1, 0)),
            ('INSERT INTO supplier_products VALUES(?,?,?)', (999, self.product, 0)),
        ]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql, params)


if __name__ == '__main__':
    unittest.main()
