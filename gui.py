"""
GUI Application for Inventory Management System (Tkinter)
Author: Sujal (BSc.IT)
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from typing import Callable, Optional
import csv
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import json
import tkinter.font as tkfont

from db import Database, _get_app_dir
from services import InventoryService
from warehouse_ui import ScrollPage, Choice, Table, saved, export_rows, WarehouseDialog, WarehousesTab, TransactionsTab, ReportsTab


def format_currency(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


SETTINGS_FILE = _get_app_dir() / "settings.json"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def enable_treeview_sort(tree: ttk.Treeview) -> None:
    def sortby(col_id: str, reverse: bool) -> None:
        rows = [(tree.set(k, col_id), k) for k in tree.get_children("")]

        def parse_val(v: str):
            try:
                s = v.replace(",", "").strip()
                if s and not s[0].isdigit() and s[0] in {"€", "$", "€", "£"}:
                    s = s[1:]
                return float(s)
            except Exception:
                return v.lower()

        rows.sort(key=lambda t: parse_val(t[0]), reverse=reverse)
        for idx, (_, k) in enumerate(rows):
            tree.move(k, "", idx)
        tree.heading(col_id, command=lambda: sortby(col_id, not reverse))

    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: sortby(c, False))


def refresh_after_save(parent, refresh: Callable[[], None]) -> None:
    """Report refresh failures without misreporting a committed operation."""
    try:
        refresh()
    except Exception as e:
        messagebox.showwarning(
            "Refresh failed",
            f"Changes saved, but the display could not be updated: {e}",
            parent=parent,
        )


class ProductsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, service: InventoryService, currency_symbol: str, on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.service = service
        self.on_change = on_change
        self.currency_symbol = currency_symbol

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.search_var = tk.StringVar()
        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(search_frame, text="Find", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(search_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=(6, 0))

        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky="ew", padx=10)
        ttk.Button(buttons, text="Add", command=self.add_product).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Edit", command=self.edit_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Delete", command=self.delete_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side=tk.LEFT)

        columns = ("id", "name", "sku", "description")
        table_frame = ttk.Frame(self)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Name")
        self.tree.heading("sku", text="SKU")
        self.tree.heading("description", text="Description")
        self.tree.column("id", width=50, anchor=tk.E)
        self.tree.column("name", width=260)
        self.tree.column("sku", width=140)
        self.tree.column("description", width=360)

        # Add vertical scrollbar
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Apply sorting behavior
        enable_treeview_sort(self.tree)

        # Striped rows style
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=24)
        self.tree.tag_configure("odd", background="#fbfbfb")

        self.refresh()

    def clear_search(self) -> None:
        self.search_var.set("")
        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        q = (self.search_var.get() or "").lower()
        products = self.service.list_product_catalogue()
        if q:
            products = [p for p in products if q in (p['name'] or '').lower() or q in (p.get('sku') or '').lower()]
        for p in products:
            self.tree.insert("", tk.END, values=(p['id'], p['name'], p.get('sku') or '', p.get('description') or ''))

    def _get_selected_id(self) -> Optional[int]:
        selected = self.tree.selection()
        if not selected:
            return None
        values = self.tree.item(selected[0], 'values')
        return int(values[0])

    def add_product(self) -> None:
        ProductDialog(self, title="Add Product", on_submit=self._create_product)

    def _create_product(self, data: dict) -> None:
        try:
            self.service.add_product(data['name'], data.get('sku'), data.get('description'))
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        refresh_after_save(self, self.on_change or self.refresh)

    def edit_selected(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            messagebox.showinfo("Select", "Please select a product to edit.", parent=self)
            return
        product = self.service.get_product(product_id)
        if product is None:
            messagebox.showerror("Error", "Product not found.", parent=self)
            return
        ProductDialog(self, title="Edit Product", initial=product, on_submit=lambda d: self._update_product(product_id, d))

    def _update_product(self, product_id: int, data: dict) -> None:
        try:
            fields = {
                'name': data['name'],
                'sku': data.get('sku'),
                'description': data.get('description'),
            }
            self.service.update_product(product_id, **fields)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        refresh_after_save(self, self.on_change or self.refresh)

    def delete_selected(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            messagebox.showinfo("Select", "Please select a product to delete.", parent=self)
            return
        if not messagebox.askyesno("Confirm", "Delete selected product?", parent=self):
            return
        try:
            self.service.delete_product(product_id)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        refresh_after_save(self, self.on_change or self.refresh)

    def export_csv(self) -> None:
        products = self.service.list_product_catalogue()
        q = self.search_var.get().lower()
        products = [p for p in products if not q or q in p['name'].lower() or q in (p.get('sku') or '').lower()]
        filepath = filedialog.asksaveasfilename(parent=self, title="Export Products CSV", defaultextension=".csv", filetypes=[("CSV Files", "*.csv")], initialfile=f"products_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv")
        if not filepath:
            return
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "name", "sku", "description"])
                for p in products:
                    writer.writerow([p['id'], p['name'], p.get('sku') or '', p.get('description') or ''])
            messagebox.showinfo("Export", f"Exported to {filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


class SuppliersTab(ttk.Frame):
    def __init__(self, parent, service, on_change=None) -> None:
        super().__init__(parent)
        self.service = service
        self.on_change = on_change or self.refresh
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=8)
        ttk.Label(top, text='Supplier: ').pack(side=tk.LEFT)
        self.supplier = Choice(top, self.refresh_catalogue)
        self.supplier.pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text='Refresh', command=self.refresh).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text='Export CSV', command=self.export_csv).pack(side=tk.LEFT, padx=4)
        self.tree = Table(self, ('id', 'name', 'sku', 'description', 'purchase_price'))
        associations = ttk.LabelFrame(self, text='Product catalogue')
        associations.pack(fill='x', padx=10, pady=4)
        ttk.Label(associations, text='Product: ').pack(side=tk.LEFT, padx=4, pady=8)
        self.existing_product = Choice(associations)
        self.existing_product.pack(side=tk.LEFT, padx=4, pady=8)
        ttk.Button(associations, text='Associate existing', command=self.associate).pack(side=tk.LEFT, padx=4, pady=8)
        ttk.Button(associations, text='Remove association', command=self.unlink).pack(side=tk.LEFT, padx=4, pady=8)
        ttk.Button(associations, text='Set price', command=self.set_price).pack(side=tk.LEFT, padx=4, pady=8)
        self.tree.pack(fill='both', expand=True, padx=10, pady=8)
        self.refresh()

    def refresh(self):
        self.supplier.reload(self.service.list_suppliers())
        self.existing_product.reload(self.service.list_product_catalogue())
        self.refresh_catalogue()

    def refresh_catalogue(self):
        supplier_id = self.supplier.identifier()
        rows = self.service.list_supplier_products(supplier_id) if supplier_id is not None else []
        self.tree.reload(rows)

    def _get_selected_id(self):
        return self.supplier.identifier()

    def require_supplier(self):
        supplier_id = self.supplier.identifier()
        if supplier_id is None:
            messagebox.showinfo('Select', 'Select a supplier first.', parent=self)
        return supplier_id

    def ask_price(self, initial=0):
        return simpledialog.askfloat('Supplier price', 'Purchase price for this supplier:', initialvalue=initial, minvalue=0, parent=self)

    def associate(self):
        supplier_id, product_id = self.require_supplier(), self.existing_product.identifier()
        if supplier_id is not None and product_id is not None:
            price = self.ask_price()
            if price is not None:
                saved(self, lambda: self.service.associate_supplier_product(supplier_id, product_id, price), self.on_change)

    def unlink(self):
        supplier_id, product_id = self.require_supplier(), self.tree.identifier()
        if supplier_id is not None and product_id is not None:
            saved(self, lambda: self.service.remove_supplier_product(supplier_id, product_id), self.on_change)

    def set_price(self):
        supplier_id, product_id = self.require_supplier(), self.tree.identifier()
        if supplier_id is not None and product_id is not None:
            initial = float(self.tree.item(str(product_id), 'values')[-1])
            price = self.ask_price(initial)
            if price is not None:
                saved(self, lambda: self.service.set_supplier_price(supplier_id, product_id, price), self.on_change)

    def export_csv(self):
        supplier_id = self.supplier.identifier()
        rows = self.service.list_supplier_products(supplier_id) if supplier_id is not None else []
        export_rows(self, [dict(row, supplier=self.supplier.get()) for row in rows], ('supplier', 'id', 'name', 'sku', 'description', 'purchase_price'), 'supplier_products.csv')

class EntitySettings(ttk.LabelFrame):
    def __init__(self, parent, service, kind, on_change):
        super().__init__(parent, text=kind.title())
        self.service, self.kind, self.on_change = service, kind, on_change
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=8, pady=6)
        for label, command in [('Add', self.add), ('Edit', self.edit), ('Delete', self.delete)]:
            ttk.Button(bar, text=label, command=command).pack(side=tk.LEFT, padx=4)
        columns = ('id', 'name', 'address') if kind == 'warehouse' else ('id', 'name', 'contact_name', 'phone', 'email', 'address')
        self.tree = Table(self, columns, height=4)
        self.tree.pack(fill='both', expand=True, padx=8, pady=6)
        self.refresh()

    def refresh(self):
        self.tree.reload(getattr(self.service, 'list_'+self.kind+'s')())

    def changed(self):
        self.refresh()
        self.on_change()

    def add(self):
        self.open_dialog()

    def edit(self):
        identifier = self.tree.identifier()
        if identifier is not None:
            self.open_dialog(identifier)

    def open_dialog(self, identifier=None):
        initial = getattr(self.service, 'get_'+self.kind)(identifier) if identifier is not None else None
        def submit(data):
            if identifier is None:
                action = lambda: getattr(self.service, 'add_'+self.kind)(**data)
            else:
                action = lambda: getattr(self.service, 'update_'+self.kind)(identifier, **data)
            return saved(self, action, self.changed)
        if self.kind == 'supplier':
            SupplierDialog(self, 'Supplier', submit, initial)
        else:
            WarehouseDialog(self, lambda name, address: submit({'name': name, 'address': address}), initial)

    def delete(self):
        identifier = self.tree.identifier()
        if identifier is not None and messagebox.askyesno('Confirm', f'Delete selected {self.kind}? Existing stock or movement history may prevent deletion.', parent=self):
            saved(self, lambda: getattr(self.service, 'delete_'+self.kind)(identifier), self.changed)


class SettingsTab(ttk.Frame):
    def __init__(self, parent, on_currency_change, service, on_suppliers_change, on_warehouses_change) -> None:
        super().__init__(parent)
        self.on_currency_change = on_currency_change
        settings = load_settings()
        self.currency_var = tk.StringVar(value=settings.get("currency", "€"))

        ttk.Label(self, text="Currency symbol:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=(12, 6))
        ttk.Entry(self, textvariable=self.currency_var, width=10).grid(row=0, column=1, padx=8, pady=(12, 6))
        ttk.Button(self, text="Save", command=self.save).grid(row=0, column=2, padx=8, pady=(12, 6))

        ttk.Label(self, text="Backup database:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Button(self, text="Create backup", command=self.backup_db).grid(row=1, column=1, padx=8, pady=6)

        self.grid_columnconfigure(3, weight=1)

        self.supplier_settings = EntitySettings(self, service, 'supplier', on_suppliers_change)
        self.supplier_settings.grid(row=2, column=0, columnspan=4, sticky='nsew', padx=10, pady=8)
        self.warehouse_settings = EntitySettings(self, service, 'warehouse', on_warehouses_change)
        self.warehouse_settings.grid(row=3, column=0, columnspan=4, sticky='nsew', padx=10, pady=8)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=1)

    def refresh(self):
        self.supplier_settings.refresh()
        self.warehouse_settings.refresh()

    def save(self) -> None:
        symbol = self.currency_var.get().strip() or "€"
        settings = load_settings()
        settings["currency"] = symbol
        save_settings(settings)
        self.on_currency_change(symbol)
        messagebox.showinfo("Saved", "Settings updated.", parent=self)

    def backup_db(self) -> None:
        db_file = Path(self.service.db.db_path)
        if not db_file.exists():
            messagebox.showerror("Error", "Database not found.", parent=self)
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        default_name = f"inventory_{timestamp}.db"
        filepath = filedialog.asksaveasfilename(parent=self, title="Save backup", defaultextension=".db", filetypes=[("SQLite DB", "*.db")], initialfile=default_name)
        if not filepath:
            return
        try:
            if Path(filepath).resolve() == db_file.resolve():
                raise ValueError("Choose a different file for the backup.")
            with sqlite3.connect(db_file) as source, sqlite3.connect(filepath) as target:
                source.backup(target)
            messagebox.showinfo("Backup", f"Backup saved: {filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


class ProductDialog(tk.Toplevel):
    def __init__(self, parent: ProductsTab, title: str, on_submit, initial: Optional[dict] = None, supplier_price: bool = False) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.on_submit = on_submit

        self.name_var = tk.StringVar(value=(initial or {}).get('name') or '')
        self.sku_var = tk.StringVar(value=(initial or {}).get('sku') or '')
        self.desc_var = tk.StringVar(value=(initial or {}).get('description') or '')
        self.supplier_price = supplier_price
        self.price_var = tk.StringVar(value='0')

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ttk.Label(body, text="Name:").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.name_var, width=40).grid(row=0, column=1, pady=4)
        ttk.Label(body, text="SKU:").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.sku_var, width=40).grid(row=1, column=1, pady=4)
        ttk.Label(body, text="Description:").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.desc_var, width=40).grid(row=2, column=1, pady=4)
        if supplier_price:
            ttk.Label(body, text="Supplier purchase price:").grid(row=3, column=0, sticky=tk.W, pady=4)
            ttk.Entry(body, textvariable=self.price_var, width=20).grid(row=3, column=1, sticky=tk.W, pady=4)

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Save", command=self._save).pack(side=tk.RIGHT, padx=8)

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _save(self) -> None:
        data = {
            'name': self.name_var.get().strip(),
            'sku': self.sku_var.get().strip() or None,
            'description': self.desc_var.get().strip() or None,
        }
        if not data['name']:
            messagebox.showerror("Error", "Name is required.", parent=self)
            return
        if self.supplier_price:
            try:
                data['purchase_price'] = float(self.price_var.get())
            except ValueError:
                messagebox.showerror('Error', 'Enter a valid purchase price.', parent=self)
                return
        if self.on_submit(data) is not False:
            self.destroy()


class SupplierDialog(tk.Toplevel):
    def __init__(self, parent: SuppliersTab, title: str, on_submit, initial: Optional[dict] = None) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.on_submit = on_submit

        self.name_var = tk.StringVar(value=(initial or {}).get('name') or '')
        self.contact_var = tk.StringVar(value=(initial or {}).get('contact_name') or '')
        self.phone_var = tk.StringVar(value=(initial or {}).get('phone') or '')
        self.email_var = tk.StringVar(value=(initial or {}).get('email') or '')
        self.address_var = tk.StringVar(value=(initial or {}).get('address') or '')

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ttk.Label(body, text="Name:").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.name_var, width=40).grid(row=0, column=1, pady=4)
        ttk.Label(body, text="Contact:").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.contact_var, width=40).grid(row=1, column=1, pady=4)
        ttk.Label(body, text="Phone:").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.phone_var, width=40).grid(row=2, column=1, pady=4)
        ttk.Label(body, text="Email:").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.email_var, width=40).grid(row=3, column=1, pady=4)
        ttk.Label(body, text="Address:").grid(row=4, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=self.address_var, width=40).grid(row=4, column=1, pady=4)

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Save", command=self._save).pack(side=tk.RIGHT, padx=8)

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _save(self) -> None:
        data = {
            'name': self.name_var.get().strip(),
            'contact_name': self.contact_var.get().strip() or None,
            'phone': self.phone_var.get().strip() or None,
            'email': self.email_var.get().strip() or None,
            'address': self.address_var.get().strip() or None,
        }
        if not data['name']:
            messagebox.showerror("Error", "Name is required.", parent=self)
            return
        if self.on_submit(data) is not False:
            self.destroy()


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Inventory Management System")
        self.geometry("1400x900")

        # Init core services
        self.database = Database()
        self.database.init_db()
        self.service = InventoryService(self.database)

        # Simple runtime settings (currency)
        self.currency_symbol = "€"

        # Apply professional styling
        self._apply_style()

        # Menu bar
        self._build_menu()

        # Notebook tabs
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook = notebook

        # Reserve the status bar before the notebook consumes available space.
        notebook.pack_forget()
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken")
        status.pack(side=tk.BOTTOM, fill=tk.X)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_pages = {}
        def add_tab(attribute, label, factory):
            page = ScrollPage(notebook)
            tab = factory(page.content)
            tab.pack(fill=tk.BOTH, expand=True)
            setattr(self, attribute, tab)
            if hasattr(tab, 'refresh'):
                page.refresh = tab.refresh
            self.tab_pages[attribute] = page
            notebook.add(page, text=label)

        add_tab('warehouses_tab', 'Warehouses', lambda parent: WarehousesTab(parent, self.service, self._on_warehouses_changed))
        add_tab('products_tab', 'Products', lambda parent: ProductsTab(parent, self.service, self.currency_symbol, self._on_products_changed))
        add_tab('suppliers_tab', 'Suppliers', lambda parent: SuppliersTab(parent, self.service, self._on_suppliers_changed))
        add_tab('transactions_tab', 'Transactions', lambda parent: TransactionsTab(parent, self.service, self.currency_symbol, self._on_transaction_recorded))
        add_tab('reports_tab', 'Reports', lambda parent: ReportsTab(parent, self.service, self.currency_symbol))
        add_tab('settings_tab', 'Settings', lambda parent: SettingsTab(parent, self._on_currency_change, self.service, self._on_suppliers_changed, self._on_warehouses_changed))

        notebook.select(self.tab_pages['warehouses_tab'])

        # Center window
        self.after(50, self._center_on_screen)

        # Global shortcuts
        self.bind_all("<F5>", lambda e: self.refresh_current_tab())
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _apply_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        # Fonts
        default_font = tkfont.nametofont("TkDefaultFont")
        family = "Segoe UI" if "Segoe UI" in tkfont.families() else default_font.cget("family")
        size = max(10, default_font.cget("size"))
        default_font.configure(family=family, size=size)
        heading_font = tkfont.Font(family=family, size=size, weight="bold")
        style.configure("TButton", padding=6)
        style.configure("Treeview", rowheight=26, font=default_font)
        style.configure("Treeview.Heading", font=heading_font)
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Backup Database", command=self._menu_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Refresh (F5)", command=self.refresh_current_tab)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _menu_backup(self) -> None:
        # Delegate to settings tab backup
        try:
            self.settings_tab.backup_db()
            self.set_status("Backup created")
        except Exception:
            pass

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Inventory Management System\nBuilt with Python, Tkinter, and SQLite\nAuthor: Sujal",
            parent=self,
        )

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _refresh_tabs_after_save(self, *tabs) -> None:
        # A failure in one view must not prevent the others from updating.
        for tab in tabs:
            refresh_after_save(self, tab.refresh)

    def _on_products_changed(self) -> None:
        self._refresh_tabs_after_save(self.products_tab, self.suppliers_tab, self.warehouses_tab, self.transactions_tab, self.reports_tab)

    def _on_suppliers_changed(self) -> None:
        self._refresh_tabs_after_save(self.suppliers_tab, self.products_tab, self.warehouses_tab, self.transactions_tab, self.reports_tab)

    def _on_warehouses_changed(self) -> None:
        self._refresh_tabs_after_save(self.warehouses_tab, self.products_tab, self.transactions_tab, self.reports_tab)

    def _on_transaction_recorded(self) -> None:
        self._refresh_tabs_after_save(self.products_tab, self.suppliers_tab, self.warehouses_tab, self.transactions_tab, self.reports_tab)

    def refresh_current_tab(self) -> None:
        tab = self.notebook.nametowidget(self.notebook.select())
        if hasattr(tab, "refresh"):
            try:
                tab.refresh()
                self.set_status("Refreshed")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    def _center_on_screen(self) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # Leave room for the title bar, desktop panels and taskbar.
        available_width = max(1, sw - 80)
        available_height = max(1, sh - 120)
        required_width = self.winfo_reqwidth()
        required_height = self.winfo_reqheight()
        w = min(max(1400, required_width), available_width)
        h = min(max(900, required_height), available_height)
        self.minsize(min(480, available_width), min(320, available_height))
        x = max(0, (sw - w) // 2)
        y = max(30, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_exit(self) -> None:
        if messagebox.askokcancel("Exit", "Quit the application?"):
            self.destroy()

    def _on_currency_change(self, symbol: str) -> None:
        self.currency_symbol = symbol
        # Update dependent tabs
        self.products_tab.currency_symbol = symbol
        self.transactions_tab.currency_symbol = symbol
        self.reports_tab.currency_symbol = symbol
        self.products_tab.refresh()
        self.reports_tab.refresh()


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
