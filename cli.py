"""
Console UI for the Inventory Management System
Author: Sujal (BSc.IT)
"""
from typing import Optional
from services import InventoryService

# Extra standard library imports for usability features
import json
import csv
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Settings handling
SETTINGS_FILE = Path(__file__).with_name("settings.json")


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _get_currency(settings: Optional[dict] = None) -> str:
    s = settings if settings is not None else _load_settings()
    return s.get("currency", "€")


def prompt_int(message: str, allow_empty: bool = False) -> Optional[int]:
    while True:
        raw = input(message).strip()
        if allow_empty and raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            print("Enter a valid integer.")


def prompt_float(message: str, allow_empty: bool = False) -> Optional[float]:
    while True:
        raw = input(message).strip()
        if allow_empty and raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print("Enter a valid number.")


def prompt_str(message: str, allow_empty: bool = False) -> Optional[str]:
    while True:
        raw = input(message).strip()
        if allow_empty or raw != "":
            return raw if raw != "" else None
        print("This field cannot be empty.")


def pause() -> None:
    input("Press Enter to continue...")


def confirm(message: str) -> bool:
    answer = input(f"{message} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def format_currency(value: float) -> str:
    return f"{_get_currency()}{value:,.2f}"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def export_csv(filename: str, headers: list[str], rows: list[list[object]]) -> Path:
    export_dir = Path(__file__).with_name("exports")
    ensure_dir(export_dir)
    export_path = export_dir / filename
    with export_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return export_path


def parse_date_input(prompt: str) -> Optional[datetime]:
    raw = input(prompt).strip()
    if raw == "":
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print("Invalid date format. Use YYYY-MM-DD.")
        return None


def ask_date_range() -> Optional[tuple[datetime, datetime]]:
    print("Enter date range (YYYY-MM-DD). Leave blank to cancel.")
    start = parse_date_input("Start date: ")
    if start is None:
        return None
    end = parse_date_input("End date: ")
    if end is None:
        return None
    if end < start:
        print("End date must be on or after start date.")
        return None
    # Inclusive end of day
    end = end.replace(hour=23, minute=59, second=59)
    return (start, end)


def print_products(service: InventoryService) -> None:
    products = service.list_products()
    print_products_table(products)


def print_products_table(products: list[dict]) -> None:
    if not products:
        print("No products found.")
        return
    print("ID  | Name                           | SKU           | Price       | Stock | Reorder")
    print("----+---------------------------------+---------------+-------------+-------+--------")
    for p in products:
        price_str = format_currency(float(p['unit_price']))
        print(
            f"{p['id']:>3} | {p['name'][:31]:<31} | {str(p['sku'] or '')[:13]:<13} | "
            f"{price_str:>11} | {p['quantity_in_stock']:>5} | {p['reorder_level']:>6}"
        )


def manage_products(service: InventoryService) -> None:
    while True:
        print("\n-- Manage Products --")
        print("1) List products")
        print("2) Add product")
        print("3) Update product")
        print("4) Delete product")
        print("5) Search/filter products")
        print("6) Export products to CSV")
        print("0) Back")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            print_products(service)
            pause()
        elif choice == "2":
            name = prompt_str("Name: ")
            sku = prompt_str("SKU (optional): ", allow_empty=True)
            desc = prompt_str("Description (optional): ", allow_empty=True)
            price = prompt_float("Unit price: ")
            reorder = prompt_int("Reorder level (0+): ")
            try:
                service.add_product(name or "", sku, desc, price or 0.0, reorder or 0)
                print("Product added.")
            except Exception as e:
                print(f"Error: {e}")
            pause()
        elif choice == "3":
            print_products(service)
            pid = prompt_int("Product ID to update: ")
            if pid is None:
                continue
            name = prompt_str("New name (optional): ", allow_empty=True)
            sku = prompt_str("New SKU (optional): ", allow_empty=True)
            desc = prompt_str("New description (optional): ", allow_empty=True)
            price = prompt_float("New unit price (optional): ", allow_empty=True)
            reorder = prompt_int("New reorder level (optional): ", allow_empty=True)
            fields = {}
            if name is not None:
                fields["name"] = name
            if sku is not None:
                fields["sku"] = sku
            if desc is not None:
                fields["description"] = desc
            if price is not None:
                fields["unit_price"] = price
            if reorder is not None:
                fields["reorder_level"] = reorder
            try:
                service.update_product(pid, **fields)
                print("Product updated.")
            except Exception as e:
                print(f"Error: {e}")
            pause()
        elif choice == "4":
            print_products(service)
            pid = prompt_int("Product ID to delete: ")
            if pid is None:
                continue
            if not confirm("Are you sure you want to delete this product?"):
                print("Cancelled.")
                pause()
                continue
            try:
                service.delete_product(pid)
                print("Product deleted.")
            except Exception as e:
                print(f"Error: {e}")
            pause()
        elif choice == "5":
            q = prompt_str("Search by name or SKU (case-insensitive): ", allow_empty=True)
            all_products = service.list_products()
            if q:
                ql = q.lower()
                filtered = [p for p in all_products if ql in (p['name'] or '').lower() or ql in (p.get('sku') or '').lower()]
            else:
                filtered = all_products
            print_products_table(filtered)
            pause()
        elif choice == "6":
            products = service.list_products()
            rows = [[p['id'], p['name'], p.get('sku') or '', p.get('description') or '', p['unit_price'], p['quantity_in_stock'], p['reorder_level']] for p in products]
            path = export_csv("products.csv", ["id", "name", "sku", "description", "unit_price", "quantity_in_stock", "reorder_level"], rows)
            print(f"Exported to {path}")
            pause()
        elif choice == "0":
            return
        else:
            print("Invalid option.")


def print_suppliers(service: InventoryService) -> None:
    suppliers = service.list_suppliers()
    if not suppliers:
        print("No suppliers found.")
        return
    print("ID  | Name                           | Contact         | Phone         | Email")
    print("----+---------------------------------+-----------------+---------------+------------------------------")
    for s in suppliers:
        print(
            f"{s['id']:>3} | {s['name'][:31]:<31} | {str(s.get('contact_name') or '')[:15]:<15} | "
            f"{str(s.get('phone') or '')[:13]:<13} | {str(s.get('email') or '')[:28]:<28}"
        )


def manage_suppliers(service: InventoryService) -> None:
    while True:
        print("\n-- Manage Suppliers --")
        print("1) List suppliers")
        print("2) Add supplier")
        print("3) Update supplier")
        print("4) Delete supplier")
        print("0) Back")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            print_suppliers(service)
            pause()
        elif choice == "2":
            name = prompt_str("Name: ")
            contact = prompt_str("Contact name (optional): ", allow_empty=True)
            phone = prompt_str("Phone (optional): ", allow_empty=True)
            email = prompt_str("Email (optional): ", allow_empty=True)
            address = prompt_str("Address (optional): ", allow_empty=True)
            try:
                service.add_supplier(name or "", contact, phone, email, address)
                print("Supplier added.")
            except Exception as e:
                print(f"Error: {e}")
            pause()
        elif choice == "3":
            print_suppliers(service)
            sid = prompt_int("Supplier ID to update: ")
            if sid is None:
                continue
            name = prompt_str("New name (optional): ", allow_empty=True)
            contact = prompt_str("New contact (optional): ", allow_empty=True)
            phone = prompt_str("New phone (optional): ", allow_empty=True)
            email = prompt_str("New email (optional): ", allow_empty=True)
            address = prompt_str("New address (optional): ", allow_empty=True)
            fields = {}
            if name is not None:
                fields["name"] = name
            if contact is not None:
                fields["contact_name"] = contact
            if phone is not None:
                fields["phone"] = phone
            if email is not None:
                fields["email"] = email
            if address is not None:
                fields["address"] = address
            try:
                service.update_supplier(sid, **fields)
                print("Supplier updated.")
            except Exception as e:
                print(f"Error: {e}")
            pause()
        elif choice == "4":
            print_suppliers(service)
            sid = prompt_int("Supplier ID to delete: ")
            if sid is None:
                continue
            try:
                service.delete_supplier(sid)
                print("Supplier deleted.")
            except Exception as e:
                print(f"Error: {e}")
            pause()
        elif choice == "0":
            return
        else:
            print("Invalid option.")


def record_purchase(service: InventoryService) -> None:
    print_products(service)
    pid = prompt_int("Product ID: ")
    print_suppliers(service)
    sid = prompt_int("Supplier ID (optional, Enter to skip): ", allow_empty=True)
    qty = prompt_int("Quantity: ")
    cost = prompt_float("Unit cost: ")
    try:
        service.record_purchase(pid or 0, qty or 0, cost or 0.0, sid)
        print("Purchase recorded and stock updated.")
    except Exception as e:
        print(f"Error: {e}")
    pause()


def record_sale(service: InventoryService) -> None:
    print_products(service)
    pid = prompt_int("Product ID: ")
    qty = prompt_int("Quantity: ")
    price = prompt_float("Unit price: ")
    customer = prompt_str("Customer name (optional): ", allow_empty=True)
    notes = prompt_str("Notes (optional): ", allow_empty=True)
    try:
        service.record_sale(pid or 0, qty or 0, price or 0.0, customer, notes)
        print("Sale recorded and stock updated.")
    except Exception as e:
        print(f"Error: {e}")
    pause()


def reports_menu(service: InventoryService) -> None:
    while True:
        print("\n-- Reports --")
        print("1) Stock levels")
        print("2) Low stock items")
        print("3) Sales summary")
        print("4) Sales between dates")
        print("5) Purchases between dates")
        print("6) Export stock to CSV")
        print("7) Export low stock to CSV")
        print("8) Export sales summary to CSV")
        print("0) Back")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            print_products(service)
            pause()
        elif choice == "2":
            low = service.report_low_stock()
            if not low:
                print("No low stock items.")
            else:
                print("ID  | Name                           | Stock | Reorder")
                print("----+---------------------------------+-------+--------")
                for p in low:
                    print(f"{p['id']:>3} | {p['name'][:31]:<31} | {p['quantity_in_stock']:>5} | {p['reorder_level']:>6}")
            pause()
        elif choice == "3":
            summary = service.report_sales_summary()
            if not summary:
                print("No sales yet.")
            else:
                print("Product                          | Qty Sold | Revenue")
                print("---------------------------------+----------+---------")
                for r in summary:
                    revenue_str = format_currency(float(r['total_revenue'] or 0))
                    print(f"{r['product_name'][:33]:<33} | {int(r['total_quantity_sold'] or 0):>8} | {revenue_str:>9}")
            pause()
        elif choice == "4":
            rng = ask_date_range()
            if not rng:
                continue
            start, end = rng
            sales = service.report_sales_between(start.isoformat(), end.isoformat())
            if not sales:
                print("No sales in this range.")
            else:
                print("Date & Time (UTC)        | Product                        | Qty | Unit Price  | Customer")
                print("-------------------------+---------------------------------+-----+-------------+------------------")
                for s in sales:
                    price_str = format_currency(float(s['unit_price']))
                    print(f"{s['sold_at'][:23]:<23} | {s['product_name'][:33]:<33} | {s['quantity']:>3} | {price_str:>11} | {(s.get('customer_name') or '')[:16]:<16}")
            pause()
        elif choice == "5":
            rng = ask_date_range()
            if not rng:
                continue
            start, end = rng
            purchases = service.report_purchases_between(start.isoformat(), end.isoformat())
            if not purchases:
                print("No purchases in this range.")
            else:
                print("Date & Time (UTC)        | Product                        | Qty | Unit Cost   | Supplier")
                print("-------------------------+---------------------------------+-----+-------------+------------------")
                for p in purchases:
                    cost_str = format_currency(float(p['unit_cost']))
                    print(f"{p['purchased_at'][:23]:<23} | {p['product_name'][:33]:<33} | {p['quantity']:>3} | {cost_str:>11} | {(p.get('supplier_name') or '')[:16]:<16}")
            pause()
        elif choice == "6":
            products = service.report_stock_levels()
            rows = [[p['id'], p['name'], p.get('sku') or '', p['unit_price'], p['quantity_in_stock'], p['reorder_level']] for p in products]
            path = export_csv("stock_levels.csv", ["id", "name", "sku", "unit_price", "quantity_in_stock", "reorder_level"], rows)
            print(f"Exported to {path}")
            pause()
        elif choice == "7":
            low = service.report_low_stock()
            rows = [[p['id'], p['name'], p.get('sku') or '', p['quantity_in_stock'], p['reorder_level']] for p in low]
            path = export_csv("low_stock.csv", ["id", "name", "sku", "quantity_in_stock", "reorder_level"], rows)
            print(f"Exported to {path}")
            pause()
        elif choice == "8":
            summary = service.report_sales_summary()
            rows = [[r['product_name'], int(r['total_quantity_sold'] or 0), float(r['total_revenue'] or 0.0)] for r in summary]
            path = export_csv("sales_summary.csv", ["product_name", "total_quantity_sold", "total_revenue"], rows)
            print(f"Exported to {path}")
            pause()
        elif choice == "0":
            return
        else:
            print("Invalid option.")


def utilities_menu() -> None:
    while True:
        print("\n-- Utilities --")
        print("1) Backup database")
        print("2) Change currency symbol")
        print("0) Back")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            db_file = Path(__file__).with_name("inventory.db")
            if not db_file.exists():
                print("Database file not found.")
                pause()
                continue
            backups_dir = Path(__file__).with_name("backups")
            ensure_dir(backups_dir)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = backups_dir / f"inventory_{timestamp}.db"
            shutil.copy2(db_file, backup_path)
            print(f"Backup created: {backup_path}")
            pause()
        elif choice == "2":
            settings = _load_settings()
            current = settings.get("currency", "€")
            print(f"Current currency symbol: {current}")
            new_symbol = input("Enter new currency symbol (e.g., €, $, €, £): ").strip()
            if new_symbol:
                settings["currency"] = new_symbol
                _save_settings(settings)
                print("Currency updated.")
            else:
                print("No change.")
            pause()
        elif choice == "0":
            return
        else:
            print("Invalid option.")


def run(service: InventoryService) -> None:
    while True:
        print("\n== Inventory Management System ==")
        print("1) Manage Products")
        print("2) Manage Suppliers")
        print("3) Record Purchase")
        print("4) Record Sale")
        print("5) Reports")
        print("6) Utilities")
        print("0) Exit")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            manage_products(service)
        elif choice == "2":
            manage_suppliers(service)
        elif choice == "3":
            record_purchase(service)
        elif choice == "4":
            record_sale(service)
        elif choice == "5":
            reports_menu(service)
        elif choice == "6":
            utilities_menu()
        elif choice == "0":
            print("Goodbye!")
            return
        else:
            print("Invalid option.") 