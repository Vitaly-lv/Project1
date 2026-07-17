import sqlite3
import json
import re

db = r"C:\Users\Vitaly\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("TABLES:", [r[0] for r in cur.fetchall()])

patterns = ["archiv", "workspace", "Workspace", "project", "Project", "glass", "Glass"]
for pat in patterns:
    for row in cur.execute(
        "SELECT key, length(value) FROM ItemTable WHERE lower(key) LIKE ? ORDER BY key",
        (f"%{pat.lower()}%",),
    ):
        print(f"{row[0]} ({row[1]} bytes)")

print("\n--- Searching values for Project1 ---")
for row in cur.execute("SELECT key, value FROM ItemTable"):
    key, val = row
    if isinstance(val, bytes):
        try:
            val = val.decode("utf-8", errors="ignore")
        except Exception:
            continue
    if "Project1" in val or "archiv" in val.lower():
        print(f"\nKEY: {key}")
        if len(val) > 2000:
            print(val[:2000] + "...")
        else:
            print(val)

conn.close()
