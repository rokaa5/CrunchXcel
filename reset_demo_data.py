"""One-time reset of demo operational data. Run explicitly: python reset_demo_data.py --confirm"""
import argparse
import shutil
import sqlite3
from datetime import datetime
from database import DB_PATH

CLEAR_TABLES = (
    "refunds", "visits", "trainer_sessions", "sale_items",
    "purchases", "payments", "memberships", "sales", "customers",
)

def main():
    parser = argparse.ArgumentParser(description="Clear operational data, preserving catalog and configuration.")
    parser.add_argument("--confirm", action="store_true", help="Back up and delete all customer and transaction records.")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Nothing deleted. Pass --confirm to perform the reset.")
    if not DB_PATH.exists():
        parser.error(f"Database not found: {DB_PATH}")
    backup = DB_PATH.with_name(f"{DB_PATH.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{DB_PATH.suffix}")
    shutil.copy2(DB_PATH, backup)
    db = sqlite3.connect(DB_PATH)
    try:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("BEGIN IMMEDIATE")
        existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in CLEAR_TABLES:
            if table in existing:
                db.execute(f"DELETE FROM {table}")
                if "sqlite_sequence" in existing:
                    db.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        errors = db.execute("PRAGMA foreign_key_check").fetchall()
        if errors:
            raise RuntimeError(f"Foreign key errors after reset: {errors}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Operational data reset complete. Backup: {backup}")
    print("Products/services, trainers, discount rules, and login accounts preserved.")

if __name__ == "__main__":
    main()
