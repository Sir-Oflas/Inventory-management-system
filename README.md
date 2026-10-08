# Inventory Management System (GUI + SQLite)

# Author : Sujal Mandal

A Tkinter inventory application tracking warehouse stock, sales, purchases, transfers and supplier catalogues.

- Developed in Python
- Uses SQLite for local database storage (file `inventory.db`)
- Built as a personal project during BSc.IT studies by Sujal

## Features
- Shared product and supplier catalogue; a product can belong to multiple suppliers.
- Independent warehouses with local stock, reorder thresholds and low-stock reports.
- Purchases filtered by supplier catalogue and credited to a destination warehouse.
- Sales filtered by positive stock in the selected source warehouse.
- Immediate transfers with confirmation, searchable history and CSV export.
- Purchases and transfers add to destination stock and preserve existing local thresholds.
- Atomic movements, positive integer quantities and protection against negative stock.
- Products contains only the shared product identity (name, SKU, description).
- Suppliers shows a selected supplier catalogue with purchase prices and product/supplier CRUD.
- Warehouses shows local stock entries; Reports and exports support warehouse filters.
- Automatic refresh of related tabs, currency settings and database backup.

## Multi-warehouse setup
This test version uses a new database schema and includes no migration. Before the
first launch of this version, manually remove the old `inventory.db`. The app does
not delete it automatically. CLI support is not updated; use the GUI.

1. Create products in **Products** and suppliers in **Settings**.
2. Select a supplier in **Suppliers**, associate existing products or create new ones, and set their supplier purchase prices.
3. Manage supplier and warehouse identities in **Settings**; no default warehouse is created. **Warehouses** is the initial operational view.
4. Choose a warehouse from the dropdown, select a product in its stock grid and click **Set reorder level**. The warehouse grid shows only existing stock/configuration entries, including exhausted products.
5. In **Transactions**, choose supplier, catalogue product and destination for a
   purchase; choose source warehouse and an available product for a sale.
6. Use **Transfer** to move stock between different warehouses. Destination stock
   is incremented, source stock is decremented, and the total stays unchanged.

Missing product–warehouse stock entries mean quantity zero and reorder level zero.
Low-stock alerts use quantity <= local reorder level, including zero defaults.
Warehouses and products with positive stock or movement history cannot be deleted.
Suppliers with purchase history cannot be deleted. Purchase prices belong to supplier–product associations and prefill the purchase
form; you can override the cost for a single purchase. Historical costs remain
unchanged when catalogue prices change. Sale prices are entered per sale.
Removing a catalogue association
only prevents future purchases from that supplier; historical purchases remain.
Transfers do not generate purchases, sales or revenue. Quantities are whole units.

## Verification
Run headless tests with `python3 -m unittest discover -s tests -v`.
Run the real-widget integration check with `python3 tests/gui_smoke.py` in a GUI
session. It uses a temporary database and does not modify `inventory.db`.

## Requirements
- Python 3.9+
- No external dependencies required

## Quick Start
1. Open a terminal in the project directory.
2. Run the app:
   ```bash
   python main.py
   ```
3. The database (`inventory.db`) will be initialized on first run.

## Project Structure
- `main.py`: Entry point; starts the GUI
- `gui.py`: Main window, products and suppliers
- `warehouse_ui.py`: Warehouses, catalogues, transactions and reports
- `db.py`: Database helper and schema initialization
- `dao.py`: Data Access Objects for Products, Suppliers, Purchases, Sales
- `services.py`: Business logic and validations
- `cli.py`: Console menus and user interaction

## Backups
The app stores data in `inventory.db` in this folder. Back up this file to save your data.

## Notes
- All timestamps are stored in ISO 8601 format (UTC).
- Monetary values are stored as REAL in SQLite; for production systems, consider using DECIMAL-like handling. 

## GUI Usage
- Run GUI via:
  ```bash
  python main.py
  ```
  Launches the GUI directly, or run the packaged `dist/InventoryGUI.exe` if built.

## Upload to GitHub
1. Create a new repository on GitHub (no README/License to avoid conflicts)
2. Initialize and push locally:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Inventory Management System (Python + SQLite + Tkinter GUI)"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```

The `.gitignore` excludes build folders, binaries, caches, and local databases.

## Build a Windows .exe (optional)

If you want a single-file executable to run on this computer without Python:

1. Install PyInstaller (one-time):
   ```bash
   pip install pyinstaller
   ```
2. Build the exe:
   ```bash
   pyinstaller --onefile --name InventoryIMS main.py
   ```
3. Find the executable in the `dist/` folder as `InventoryIMS.exe`.
4. Place `InventoryIMS.exe` anywhere (e.g., Desktop). It will create/use `inventory.db` next to the exe.
5. Optional folders `exports/`, `backups/`, and `settings.json` will also appear next to the exe when used. 
