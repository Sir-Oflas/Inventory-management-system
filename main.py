#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventory Management System - Main Entry Point
Author: Sujal
Created during BSc.IT studies
"""

# ------------------------------------------------------------------
# MODALITÀ ORIGINALE GUI / CLI
# Conservata per eventuale utilizzo futuro.
# Per riattivarla, ripristinare gli import e il blocco main originale.
# ------------------------------------------------------------------

# from db import Database
# from services import InventoryService
# import cli
#
#
# def main():
#     print("Choose mode:")
#     print("1) GUI (recommended)")
#     print("2) Console (CLI)")
#     choice = input("Enter 1 or 2 (default 1): ").strip() or "1"
#
#     if choice == "2":
#         db = Database()
#         db.init_db()
#         service = InventoryService(db)
#         cli.run(service)
#     else:
#         from gui import main as gui_main
#         gui_main()


# ------------------------------------------------------------------
# MODALITÀ WINDOWS PORTABLE
# Avvia direttamente l'interfaccia grafica.
# Questa modalità permette di compilare con PyInstaller --windowed,
# evitando l'apertura della finestra del terminale.
# ------------------------------------------------------------------

def main():
    from gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
