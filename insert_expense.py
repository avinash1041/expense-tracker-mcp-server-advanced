import sqlite3, json, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")

cur = conn.execute(
    """INSERT INTO expenses
       (date, amount, category, subcategory, note, currency, tags, is_recurring, recurrence_interval)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    ("2025-05-03", 200.0, "Groceries", "Food", "Food expense", "INR", "", 0, None),
)
new_id = cur.lastrowid
conn.execute(
    "INSERT INTO audit_log(action, table_name, record_id, payload) VALUES (?,?,?,?)",
    ("INSERT", "expenses", new_id, json.dumps({
        "date": "2025-05-03", "amount": 200.0, "category": "Groceries",
        "subcategory": "Food", "note": "Food expense", "currency": "INR"
    })),
)
conn.commit()
row = dict(conn.execute("SELECT * FROM expenses WHERE id=?", (new_id,)).fetchone())
print(f"SUCCESS: Inserted expense id={new_id}")
print(f"Row: {row}")
conn.close()
