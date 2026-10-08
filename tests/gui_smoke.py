"""Exercise real Tk widgets against a temporary database, never inventory.db."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import Database
from gui import MainWindow, ProductDialog
from warehouse_ui import WarehouseDialog

with tempfile.TemporaryDirectory() as directory:
    database = Database(Path(directory)/'smoke.db')
    with patch('gui.Database', return_value=database), patch('gui.messagebox.showinfo'), patch('warehouse_ui.messagebox.showinfo'), patch('warehouse_ui.messagebox.askyesno', return_value=True):
        window = MainWindow()
        errors = []
        window.report_callback_exception = lambda *args: errors.append(args)
        window.update()
        assert window.notebook.select() == str(window.tab_pages['warehouses_tab'])
        assert tuple(window.settings_tab.supplier_settings.tree['columns']) == ('id', 'name', 'contact_name', 'phone', 'email', 'address')
        for form in window.transactions_tab.forms.values():
            assert str(form['button']['state']) == 'disabled'
        service = window.service
        product = service.add_product('Widget', 'W', None)
        supplier = service.add_supplier('Supplier')
        service.associate_supplier_product(supplier, product)
        a = service.add_warehouse('North')
        b = service.add_warehouse('South')
        window._on_warehouses_changed()
        window._on_suppliers_changed()
        transactions = window.transactions_tab
        purchase = transactions.forms['purchase']
        purchase['supplier'].set(f'{supplier}: Supplier')
        purchase['destination'].set(f'{a}: North')
        transactions.refresh_choices()
        purchase['product'].set(f'{product}: Widget')
        purchase['quantity'].set('10')
        purchase['unit_cost'].set('3')
        transactions.record('purchase')
        assert service.get_stock(product, a) == 10
        transfer = transactions.forms['transfer']
        transfer['source'].set(f'{a}: North')
        transfer['destination'].set(f'{b}: South')
        transactions.refresh_choices()
        transfer['product'].set(f'{product}: Widget')
        transfer['quantity'].set('4')
        transactions.record('transfer')
        assert service.get_stock(product, a) == 6
        assert service.get_stock(product, b) == 4
        sale = transactions.forms['sale']
        sale['source'].set(f'{b}: South')
        transactions.refresh_choices()
        sale['product'].set(f'{product}: Widget')
        sale['quantity'].set('2')
        sale['unit_price'].set('10')
        transactions.record('sale')
        assert service.get_stock(product, b) == 2
        assert len(transactions.history_tree.get_children()) == 1
        assert purchase['quantity'].get() == '10'
        window.products_tab.refresh()
        assert tuple(window.products_tab.tree['columns']) == ('id', 'name', 'sku', 'description')
        window.suppliers_tab.supplier.set(f'{supplier}: Supplier')
        window.suppliers_tab.refresh_catalogue()
        assert len(window.suppliers_tab.tree.get_children()) == 1
        service.set_supplier_price(supplier, product, 7)
        window._on_suppliers_changed()
        assert window.suppliers_tab.tree.item(str(product), 'values')[-1] == '7.0'
        window.warehouses_tab.warehouse.set(f'{b}: South')
        window.warehouses_tab.refresh_stock()
        assert str(window.warehouses_tab.reorder_button['state']) == 'disabled'
        window.warehouses_tab.stock_tree.selection_set(str(product))
        window.warehouses_tab.update_reorder_button()
        assert str(window.warehouses_tab.reorder_button['state']) == 'normal'
        with patch('warehouse_ui.simpledialog.askinteger', return_value=3):
            window.warehouses_tab.set_level()
        window._on_warehouses_changed()
        window.reports_tab.view_var.set('Low Stock')
        window.reports_tab.refresh()
        assert len(window.reports_tab.tree.get_children()) == 1
        dialogs = [ProductDialog(window.products_tab, 'Product', lambda data: None),
                   WarehouseDialog(window.warehouses_tab, lambda name, address: True)]
        window.update()
        for dialog in dialogs:
            dialog.destroy()
        window.notebook.select(window.tab_pages['transactions_tab'])
        window.refresh_current_tab()
        window.update()
        # Exercise each tab at common small display work-area sizes.
        for width, height in [(720, 480), (944, 648), (1200, 680)]:
            window.geometry(f'{width}x{height}')
            for page in window.tab_pages.values():
                window.notebook.select(page)
                window.update()
                canvas = page.canvas
                region = tuple(float(value) for value in canvas['scrollregion'].split())
                assert region[2] >= page.content.winfo_reqwidth()
                assert region[3] >= page.content.winfo_reqheight()
                assert canvas.winfo_width() <= width
                assert canvas.winfo_height() <= height
                if page.content.winfo_reqwidth() > canvas.winfo_width():
                    assert page.horizontal.winfo_ismapped()
                if page.content.winfo_reqheight() > canvas.winfo_height():
                    assert page.vertical.winfo_ismapped()
                canvas.xview_moveto(1)
                canvas.yview_moveto(1)
                window.update()
        assert not errors, errors
        window.destroy()
print('Real Tk GUI smoke passed: empty state, dialogs, purchase, transfer, sale, filters, history, refresh.')
