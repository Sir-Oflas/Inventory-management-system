"""Warehouse-aware Tkinter controls; persistence stays in InventoryService."""
import csv
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog


def center_dialog_on_screen(dialog):
    """Position a completed form before showing it to avoid a visible jump."""
    dialog.update_idletasks()
    width = dialog.winfo_reqwidth()
    height = dialog.winfo_reqheight()
    x = max(0, (dialog.winfo_screenwidth() - width) // 2)
    y = max(0, (dialog.winfo_screenheight() - height) // 2)
    dialog.geometry(f'{width}x{height}+{x}+{y}')
    dialog.deiconify()
    dialog.grab_set()


def export_rows(parent, rows, columns, filename):
    path = filedialog.asksaveasfilename(parent=parent, initialfile=filename,
        defaultextension='.csv', filetypes=[('CSV', '*.csv')])
    if not path:
        return
    try:
        with open(path, 'w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows([[row.get(key, '') for key in columns] for row in rows])
        messagebox.showinfo('Export', 'CSV exported.', parent=parent)
    except Exception as error:
        messagebox.showerror('Error', str(error), parent=parent)


class ScrollPage(ttk.Frame):
    """Fit the viewport while keeping oversized controls reachable by scrolling."""
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vertical = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
        self.content = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.canvas.bind('<Configure>', self._resize)
        self.content.bind('<Configure>', self._resize)

    def _resize(self, event=None):
        viewport_width = self.canvas.winfo_width()
        viewport_height = self.canvas.winfo_height()
        width = max(viewport_width, self.content.winfo_reqwidth())
        height = max(viewport_height, self.content.winfo_reqheight())
        self.canvas.itemconfigure(self.window, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        if width > viewport_width:
            self.horizontal.grid(row=1, column=0, sticky='ew')
        else:
            self.horizontal.grid_remove()
            self.canvas.xview_moveto(0)
        if height > viewport_height:
            self.vertical.grid(row=0, column=1, sticky='ns')
        else:
            self.vertical.grid_remove()
            self.canvas.yview_moveto(0)


class Choice(ttk.Combobox):
    def __init__(self, parent, on_select=None, all_label=None, placeholder="(select an item)"):
        self.placeholder = placeholder
        self.variable = tk.StringVar(value=all_label or placeholder)
        self.all_label = all_label
        super().__init__(parent, textvariable=self.variable, state='readonly', width=32)
        if on_select:
            self.bind('<<ComboboxSelected>>', lambda event: on_select())

    def identifier(self):
        text = self.variable.get()
        return int(text.split(':', 1)[0]) if ':' in text else None

    def reload(self, rows):
        selected = self.identifier()
        values = [f"{row['id']}: {row['name']}" for row in rows]
        values.insert(0, self.all_label or self.placeholder)
        self['values'] = values
        match = next((value for value in values if ':' in value and int(value.split(':', 1)[0]) == selected), None)
        if match:
            self.set(match)
        else:
            self.set(self.all_label or self.placeholder)


class Table(ttk.Treeview):
    def __init__(self, parent, columns, height=10):
        super().__init__(parent, columns=columns, show='headings', height=height)
        for column in columns:
            self.heading(column, text=column.replace('_', ' ').title())
            self.column(column, width=120, stretch=True)

    def reload(self, rows):
        selected = self.selection()
        self.delete(*self.get_children())
        for index, row in enumerate(rows):
            key = str(row.get('id', index))
            self.insert('', 'end', iid=key, values=[row.get(c, '') if row.get(c) is not None else '' for c in self['columns']])
        for key in selected:
            if self.exists(key):
                self.selection_add(key)

    def identifier(self):
        selected = self.selection()
        return int(selected[0]) if selected else None


def saved(parent, action, refresh):
    try:
        action()
    except Exception as error:
        messagebox.showerror('Error', str(error), parent=parent)
        return False
    try:
        refresh()
    except Exception as error:
        messagebox.showwarning('Refresh failed', f'Changes saved, but display update failed: {error}', parent=parent)
    return True


class WarehouseDialog(tk.Toplevel):
    def __init__(self, parent, submit, initial=None):
        super().__init__(parent)
        self.withdraw()
        self.title('Warehouse')
        self.transient(parent.winfo_toplevel())
        initial = initial or {}
        self.name = tk.StringVar(value=initial.get('name', ''))
        self.address = tk.StringVar(value=initial.get('address') or '')
        for index, (label, variable) in enumerate([('Name', self.name), ('Address', self.address)]):
            ttk.Label(self, text=label).grid(row=index, column=0, padx=10, pady=8)
            ttk.Entry(self, textvariable=variable, width=40).grid(row=index, column=1, padx=10, pady=8)
        def save():
            if submit(self.name.get().strip(), self.address.get().strip() or None):
                self.destroy()
        ttk.Button(self, text='Save', command=save).grid(row=2, column=1, pady=10)
        ttk.Button(self, text='Cancel', command=self.destroy).grid(row=2, column=0)
        center_dialog_on_screen(self)


class WarehousesTab(ttk.Frame):
    def __init__(self, parent, service, on_change):
        super().__init__(parent)
        self.service, self.on_change = service, on_change
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=8, pady=8)
        ttk.Label(bar, text='Warehouse: ').pack(side='left')
        self.warehouse = Choice(bar, self.refresh_stock, placeholder="(select a warehouse)")
        self.warehouse.pack(side='left', padx=4)
        ttk.Button(bar, text='Refresh', command=self.refresh).pack(side='left', padx=4)
        ttk.Label(self, text='Selected warehouse: quantities and local reorder levels').pack(anchor='w', padx=8, pady=6)
        self.stock_tree = Table(self, ('id', 'name', 'sku', 'quantity_in_stock', 'reorder_level'))
        settings = ttk.Frame(self)
        settings.pack(fill='x', padx=8, pady=8)
        self.reorder_button = ttk.Button(settings, text='Set reorder level', command=self.set_level, state='disabled')
        self.reorder_button.pack(side='left', padx=4)
        self.stock_tree.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.stock_tree.bind('<<TreeviewSelect>>', lambda event: self.update_reorder_button())
        self.refresh()

    def refresh(self):
        self.warehouse.reload(self.service.list_warehouses())
        self.refresh_stock()

    def refresh_stock(self):
        identifier = self.warehouse.identifier()
        # Clear selection when switching warehouses, even for a shared product ID.
        if identifier != getattr(self, '_selected_warehouse', None):
            self.stock_tree.selection_remove(*self.stock_tree.selection())
        self._selected_warehouse = identifier
        self.stock_tree.reload(self.service.list_warehouse_products(identifier) if identifier is not None else [])
        self.update_reorder_button()

    def update_reorder_button(self):
        valid = self.warehouse.identifier() is not None and self.stock_tree.identifier() is not None
        self.reorder_button.configure(state='normal' if valid else 'disabled')

    def set_level(self):
        warehouse, product = self.warehouse.identifier(), self.stock_tree.identifier()
        if warehouse is None or product is None:
            return
        row = next((row for row in self.service.list_warehouse_products(warehouse) if row['id'] == product), None)
        current = row['reorder_level'] if row else 0
        level = simpledialog.askinteger('Reorder', 'Local reorder level:', initialvalue=int(current), minvalue=0, parent=self)
        if level is not None:
            saved(self, lambda: self.service.set_reorder_level(product, warehouse, level), self.on_change)


class TransactionsTab(ttk.Frame):
    def __init__(self, parent, service, currency_symbol, on_change=None):
        super().__init__(parent)
        self.service, self.currency_symbol = service, currency_symbol
        self.on_change = on_change or self.refresh
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=8, pady=8)
        self.forms = {}
        self.purchase_price_key = None
        for kind, label in [('purchase', 'Record Purchase'), ('sale', 'Record Sale'), ('transfer', 'Transfer')]:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=label)
            form = {}
            self.forms[kind] = form
            choices = ['supplier', 'destination', 'product'] if kind == 'purchase' else (['source', 'product'] if kind == 'sale' else ['source', 'product', 'destination'])
            for index, key in enumerate(choices):
                ttk.Label(frame, text=key.title()).grid(row=index, column=0, padx=8, pady=6, sticky='w')
                placeholder = {
                    "supplier": "(select a supplier)",
                    "product": "(select a product)",
                    "source": "(select the source warehouse)",
                    "destination": "(select the destination warehouse)",
                }[key]
                form[key] = Choice(frame, self.refresh_choices, placeholder=placeholder)
                form[key].grid(row=index, column=1, sticky='ew', padx=8, pady=6)
            fields = ['quantity', 'unit_cost'] if kind == 'purchase' else (['quantity', 'unit_price', 'customer', 'notes'] if kind == 'sale' else ['quantity', 'notes'])
            for index, key in enumerate(fields, start=len(choices)):
                form[key] = tk.StringVar()
                ttk.Label(frame, text=key.replace('_', ' ').title()).grid(row=index, column=0, sticky='w', padx=8, pady=6)
                ttk.Entry(frame, textvariable=form[key]).grid(row=index, column=1, sticky='ew', padx=8, pady=6)
            form['availability'] = tk.StringVar()
            ttk.Label(frame, textvariable=form['availability']).grid(row=len(choices)+len(fields), column=0, columnspan=2, padx=8, pady=6)
            form['button'] = ttk.Button(frame, text=label, command=lambda kind=kind: self.record(kind))
            form['button'].grid(row=len(choices)+len(fields)+1, column=0, columnspan=2, pady=8)
            frame.columnconfigure(1, weight=1)
        history = ttk.Frame(notebook)
        notebook.add(history, text='Transfer History')
        bar = ttk.Frame(history)
        bar.pack(fill='x', pady=8)
        self.history_product = Choice(bar, self.refresh_history, 'All products')
        self.history_product.pack(side='left', padx=4)
        self.history_warehouse = Choice(bar, self.refresh_history, 'All warehouses')
        self.history_warehouse.pack(side='left', padx=4)
        ttk.Button(bar, text='Export CSV', command=self.export_history).pack(side='left')
        self.history_tree = Table(history, ('id', 'transferred_at', 'product_name', 'source_name', 'destination_name', 'quantity', 'notes'))
        self.history_tree.pack(fill='both', expand=True)
        self.refresh()

    def refresh(self):
        warehouses = self.service.list_warehouses()
        suppliers = self.service.list_suppliers()
        self.forms['purchase']['supplier'].reload(suppliers)
        for kind, form in self.forms.items():
            for key in ('source', 'destination'):
                if key in form:
                    form[key].reload(warehouses)
        self.history_product.reload(self.service.list_products())
        self.history_warehouse.reload(warehouses)
        self.refresh_choices()
        self.refresh_history()

    def refresh_choices(self):
        for kind, form in self.forms.items():
            if kind == 'purchase':
                supplier = form['supplier'].identifier()
                rows = self.service.list_supplier_products(supplier) if supplier is not None else []
            else:
                source = form['source'].identifier()
                rows = self.service.list_available_products(source) if source is not None else []
            form['product'].reload(rows)
            product = form['product'].identifier()
            if kind == 'purchase':
                price_key = (form['supplier'].identifier(), product)
                if price_key != self.purchase_price_key:
                    selected = next((row for row in rows if row['id'] == product), None)
                    form['unit_cost'].set(str(selected['purchase_price']) if selected else '')
                    self.purchase_price_key = price_key
            warehouse = form['destination' if kind == 'purchase' else 'source'].identifier()
            valid = product is not None and warehouse is not None
            parts = []
            if valid:
                parts.append(f"{'Destination stock' if kind == 'purchase' else 'Available'}: {self.service.get_stock(product, warehouse)}")
            if kind == 'transfer':
                destination = form['destination'].identifier()
                valid = valid and destination is not None and destination != warehouse
                if product is not None and destination is not None:
                    parts.append(f'Destination stock: {self.service.get_stock(product, destination)}')
            if not self.service.list_warehouses():
                parts.append('Create a warehouse in Warehouses first.')
            elif not rows:
                parts.append('No catalogue products.' if kind == 'purchase' else 'No products available in this warehouse.')
            elif kind == 'transfer' and not valid:
                parts.append('Select two different warehouses.')
            form['availability'].set(' | '.join(parts))
            form['button'].configure(state='normal' if valid else 'disabled')

    def record(self, kind):
        form = self.forms[kind]
        try:
            product = form['product'].identifier()
            quantity = int(form['quantity'].get())
            if quantity <= 0:
                raise ValueError('Quantity must be positive')
            if kind == 'purchase':
                action = lambda: self.service.record_purchase(product, quantity, float(form['unit_cost'].get()), form['supplier'].identifier(), form['destination'].identifier())
            elif kind == 'sale':
                action = lambda: self.service.record_sale(product, quantity, float(form['unit_price'].get()), form['source'].identifier(), form['customer'].get() or None, form['notes'].get() or None)
            else:
                source, destination = form['source'].identifier(), form['destination'].identifier()
                if source is None or destination is None or source == destination or product is None:
                    raise ValueError('Select a product and two different warehouses')
                available = self.service.get_stock(product, source)
                if quantity > available:
                    raise ValueError('Insufficient stock in the source warehouse')
                if not messagebox.askyesno('Confirm transfer', f"{form['product'].get()}\n{form['source'].get()} → {form['destination'].get()}\nQuantity: {quantity}\nSource: {available} → {available-quantity}\nDestination: {self.service.get_stock(product, destination)} → {self.service.get_stock(product, destination)+quantity}", parent=self):
                    return
                action = lambda: self.service.record_transfer(product, source, destination, quantity, form['notes'].get() or None)
        except Exception as error:
            messagebox.showerror('Error', str(error), parent=self)
            return
        if saved(self, action, self.on_change):
            messagebox.showinfo('Success', 'Movement recorded.', parent=self)

    def history_rows(self):
        return self.service.list_transfers(self.history_product.identifier(), self.history_warehouse.identifier())

    def refresh_history(self):
        self.history_tree.reload(self.history_rows())

    def export_history(self):
        export_rows(self, self.history_rows(), self.history_tree['columns'], 'transfers.csv')


class ReportsTab(ttk.Frame):
    def __init__(self, parent, service, currency_symbol):
        super().__init__(parent)
        self.service, self.currency_symbol = service, currency_symbol
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=8, pady=8)
        self.view_var = tk.StringVar(value='Stock Levels')
        view = ttk.Combobox(bar, textvariable=self.view_var, state='readonly', width=18,
            values=['Stock Levels', 'Low Stock', 'Sales Summary'])
        view.pack(side='left')
        view.bind('<<ComboboxSelected>>', lambda event: self.refresh())
        self.warehouse = Choice(bar, self.refresh, 'All warehouses')
        self.warehouse.pack(side='left', padx=8)
        ttk.Button(bar, text='Run', command=self.refresh).pack(side='left')
        ttk.Button(bar, text='Export CSV', command=self.export_csv).pack(side='left', padx=8)
        self.tree = None
        self.refresh()

    def rows(self):
        warehouse = self.warehouse.identifier()
        view = self.view_var.get()
        if view == 'Stock Levels':
            columns = ('name', 'quantity_in_stock', 'reorder_level')
            rows = self.service.report_stock_levels(warehouse)
        elif view == 'Low Stock':
            columns = ('warehouse_name', 'name', 'quantity_in_stock', 'reorder_level')
            rows = self.service.report_low_stock(warehouse)
        else:
            columns = ('product_name', 'total_quantity_sold', 'total_revenue')
            rows = self.service.report_sales_summary(warehouse)
        return columns, rows

    def refresh(self):
        self.warehouse.reload(self.service.list_warehouses())
        columns, rows = self.rows()
        if self.tree is None or tuple(self.tree['columns']) != columns:
            if self.tree is not None:
                self.tree.destroy()
            self.tree = Table(self, columns)
            self.tree.pack(fill='both', expand=True, padx=8, pady=8)
        # IDs need not be unique in the per-warehouse low-stock report.
        display = []
        for index, row in enumerate(rows):
            row = dict(row, id=index)
            if 'total_revenue' in row:
                row['total_revenue'] = f"{self.currency_symbol}{row['total_revenue']:,.2f}"
            display.append(row)
        self.tree.reload(display)

    def export_csv(self):
        columns, rows = self.rows()
        warehouse = self.warehouse.get()
        export_rows(self, [dict(row, warehouse=warehouse) for row in rows], ('warehouse',)+columns,
            self.view_var.get().lower().replace(' ', '_')+'.csv')
