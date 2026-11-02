"""Persistencia local de notas fiscais em SQLite."""

from datetime import datetime
from pathlib import Path
import sqlite3

from receipt_processor import Receipt

DATABASE_PATH = Path("purchases.sqlite3")


def save_receipt(receipt: Receipt, session: Path, database_path: Path = DATABASE_PATH) -> int:
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY, scanned_at TEXT NOT NULL, merchant TEXT,
                purchase_date TEXT, total REAL, source_session TEXT NOT NULL, raw_text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS purchase_items (
                id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL REFERENCES purchases(id),
                description TEXT NOT NULL, price REAL NOT NULL
            );
        """)
        cursor = connection.execute(
            "INSERT INTO purchases (scanned_at, merchant, purchase_date, total, source_session, raw_text) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), receipt.merchant, receipt.purchase_date, receipt.total, str(session), receipt.raw_text),
        )
        purchase_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO purchase_items (purchase_id, description, price) VALUES (?, ?, ?)",
            [(purchase_id, item.description, item.total_price or 0) for item in receipt.items],
        )
        connection.commit()
        return int(purchase_id)
    finally:
        connection.close()
