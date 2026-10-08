import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from gui import MainWindow, ProductsTab, SuppliersTab, EntitySettings
from warehouse_ui import Choice, TransactionsTab, ReportsTab, saved, export_rows


class Variable:
    def __init__(self, value=''):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class FakeChoice:
    def __init__(self, rows=(), all_label=None):
        self.variable = Variable()
        self.all_label = all_label
        self.loaded = False
        self.values = []
        if rows or all_label:
            self.reload(rows)
    identifier = Choice.identifier
    reload = Choice.reload
    def __setitem__(self, key, value):
        self.values = value
    def set(self, value):
        self.variable.set(value)
    def get(self):
        return self.variable.get()


class SyncTests(unittest.TestCase):
    def make_transactions(self):
        tab = TransactionsTab.__new__(TransactionsTab)
        tab.service = Mock()
        tab.service.list_warehouses.return_value = [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]
        tab.service.list_suppliers.return_value = [{'id': 3, 'name': 'Supplier'}]
        tab.service.list_supplier_products.return_value = [{'id': 4, 'name': 'Widget', 'purchase_price': 3}]
        tab.service.list_available_products.return_value = [{'id': 4, 'name': 'Widget', 'purchase_price': 3}]
        tab.service.list_products.return_value = [{'id': 4, 'name': 'Widget', 'purchase_price': 3}]
        tab.service.get_stock.return_value = 10
        tab.service.list_transfers.return_value = []
        tab.forms = {}
        tab.purchase_price_key = None
        for kind, keys in [('purchase', ['supplier', 'destination', 'product']),
                           ('sale', ['source', 'product']), ('transfer', ['source', 'product', 'destination'])]:
            form = {key: FakeChoice() for key in keys}
            for key in ['quantity', 'unit_cost', 'unit_price', 'customer', 'notes', 'availability']:
                form[key] = Variable('2' if key in ['quantity', 'unit_cost', 'unit_price'] else 'Keep me')
            form['button'] = Mock()
            tab.forms[kind] = form
        tab.history_product = FakeChoice(all_label='All products')
        tab.history_warehouse = FakeChoice(all_label='All warehouses')
        tab.history_tree = Mock()
        tab.on_change = Mock()
        tab.refresh()
        return tab

    @patch('gui.SupplierDialog')
    @patch('gui.WarehouseDialog')
    def test_settings_crud_dialogs_use_service_and_notify(self, warehouse_dialog, supplier_dialog):
        for kind, dialog, data in [('supplier', supplier_dialog, {'name': 'Supplier'}),
                                   ('warehouse', warehouse_dialog, {'name': 'Warehouse', 'address': None})]:
            panel = EntitySettings.__new__(EntitySettings)
            panel.kind, panel.service, panel.changed = kind, Mock(), Mock()
            panel.open_dialog()
            submit = dialog.call_args.args[2] if kind == 'supplier' else dialog.call_args.args[1]
            submit(data) if kind == 'supplier' else submit('Warehouse', None)
            getattr(panel.service, 'add_'+kind).assert_called_once_with(**data)
            panel.changed.assert_called_once_with()
            panel.changed.reset_mock()
            panel.open_dialog(4)
            submit = dialog.call_args.args[2] if kind == 'supplier' else dialog.call_args.args[1]
            submit(data) if kind == 'supplier' else submit('Warehouse', None)
            getattr(panel.service, 'update_'+kind).assert_called_once_with(4, **data)
            panel.changed.assert_called_once_with()

    def test_choice_preserves_id_rename_and_clears_deleted_selection(self):
        choice = FakeChoice([{'id': 1, 'name': 'Old'}])
        choice.reload([{'id': 1, 'name': 'New'}])
        self.assertEqual(choice.get(), '1: New')
        choice.reload([{'id': 2, 'name': 'Other'}])
        self.assertIsNone(choice.identifier())
        choice.reload([])
        self.assertEqual(choice.values, [])

    def test_context_filters_and_form_preservation(self):
        tab = self.make_transactions()
        tab.service.list_supplier_products.assert_called_with(3)
        tab.service.list_available_products.assert_called_with(1)
        tab.forms['transfer']['destination'].set('2: B')
        tab.refresh()
        for form in tab.forms.values():
            self.assertEqual(form['quantity'].get(), '2')
            self.assertEqual(form['notes'].get(), 'Keep me')
        tab.forms['transfer']['button'].configure.assert_called_with(state='normal')
        tab.service.list_available_products.return_value = []
        tab.refresh_choices()
        self.assertIsNone(tab.forms['sale']['product'].identifier())
        tab.forms['sale']['button'].configure.assert_called_with(state='disabled')
        tab.service.list_supplier_products.return_value = []
        tab.refresh_choices()
        tab.forms['purchase']['button'].configure.assert_called_with(state='disabled')

    def test_purchase_price_proposed_per_supplier_and_keeps_manual_override(self):
        tab = self.make_transactions()
        form = tab.forms['purchase']
        self.assertEqual(form['unit_cost'].get(), '3')
        form['unit_cost'].set('4.5')
        tab.refresh_choices()
        self.assertEqual(form['unit_cost'].get(), '4.5')
        form['supplier'].set('9: Different supplier')
        tab.service.list_supplier_products.return_value = [{'id': 4, 'name': 'Widget', 'purchase_price': 8}]
        tab.refresh_choices()
        self.assertEqual(form['unit_cost'].get(), '8')

    def test_empty_warehouse_state_blocks_movements(self):
        tab = self.make_transactions()
        tab.service.list_warehouses.return_value = []
        tab.refresh()
        for form in tab.forms.values():
            form['button'].configure.assert_called_with(state='disabled')
            self.assertIn('Create a warehouse', form['availability'].get())

    @patch('warehouse_ui.messagebox')
    def test_movement_success_failure_and_cancel(self, messages):
        tab = self.make_transactions()
        for kind, method in [('purchase', 'record_purchase'), ('sale', 'record_sale')]:
            tab.on_change.reset_mock()
            tab.record(kind)
            tab.on_change.assert_called_once_with()
            getattr(tab.service, method).side_effect = ValueError('Failed')
            tab.on_change.reset_mock()
            tab.record(kind)
            tab.on_change.assert_not_called()
        tab.forms['transfer']['destination'].set('2: B')
        messages.askyesno.return_value = False
        tab.on_change.reset_mock()
        tab.record('transfer')
        tab.on_change.assert_not_called()
        tab.service.record_transfer.assert_not_called()
        messages.askyesno.return_value = True
        tab.record('transfer')
        tab.service.record_transfer.assert_called_once_with(4, 1, 2, 2, 'Keep me')

    @patch('gui.messagebox')
    def test_coordinator_continues_and_f5_refreshes(self, messages):
        window = MainWindow.__new__(MainWindow)
        for name in ('products_tab', 'suppliers_tab', 'warehouses_tab', 'transactions_tab', 'reports_tab'):
            setattr(window, name, SimpleNamespace(refresh=Mock()))
        window.products_tab.refresh.side_effect = RuntimeError('Failed')
        window._on_transaction_recorded()
        for name in ('products_tab', 'warehouses_tab', 'transactions_tab', 'reports_tab'):
            getattr(window, name).refresh.assert_called_once_with()
        messages.showwarning.assert_called_once()
        window.notebook = Mock()
        window.notebook.nametowidget.return_value = window.transactions_tab
        window.set_status = Mock()
        window.refresh_current_tab()
        self.assertEqual(window.transactions_tab.refresh.call_count, 2)

    @patch('gui.messagebox')
    def test_crud_callback_only_on_success(self, messages):
        for cls, method, service_method in [(ProductsTab, '_create_product', 'add_product')]:
            tab = cls.__new__(cls)
            tab.service, tab.on_change = Mock(), Mock()
            data = {'name': 'New', 'unit_price': '2'}
            getattr(tab, method)(data)
            tab.on_change.assert_called_once_with()
            getattr(tab.service, service_method).side_effect = ValueError('Failed')
            tab.on_change.reset_mock()
            getattr(tab, method)(data)
            tab.on_change.assert_not_called()

    @patch('warehouse_ui.messagebox')
    def test_refresh_error_does_not_report_saved_operation_as_failed(self, messages):
        action = Mock()
        self.assertTrue(saved(None, action, Mock(side_effect=RuntimeError('Failed'))))
        action.assert_called_once_with()
        messages.showwarning.assert_called_once()
        messages.showerror.assert_not_called()

    def test_history_filters_and_report_filter_forwarding(self):
        tab = self.make_transactions()
        tab.history_product.set('4: Widget')
        tab.history_warehouse.set('2: B')
        tab.refresh_history()
        tab.service.list_transfers.assert_called_with(4, 2)
        report = ReportsTab.__new__(ReportsTab)
        report.service = Mock()
        report.warehouse = FakeChoice([{'id': 2, 'name': 'B'}])
        report.view_var = Variable('Low Stock')
        report.rows()
        report.service.report_low_stock.assert_called_once_with(2)
        report.view_var.set('Sales Summary')
        report.rows()
        report.service.report_sales_summary.assert_called_once_with(2)

    @patch('warehouse_ui.messagebox')
    @patch('warehouse_ui.filedialog.asksaveasfilename')
    def test_csv_has_filtered_warehouse_and_rows(self, dialog, messages):
        import tempfile
        import csv
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.csv'
            dialog.return_value = str(path)
            export_rows(None, [{'warehouse': '2: B', 'name': 'Widget', 'quantity_in_stock': 5}],
                        ('warehouse', 'name', 'quantity_in_stock'), 'stock.csv')
            with path.open(newline='') as stream:
                self.assertEqual(list(csv.reader(stream)), [['warehouse', 'name', 'quantity_in_stock'], ['2: B', 'Widget', '5']])


if __name__ == '__main__':
    unittest.main()
