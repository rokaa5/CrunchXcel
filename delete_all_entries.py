import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB_NAME = os.environ.get("GYM_DB_NAME", "gym.db")
DB_PATH = Path(__file__).resolve().parent / DB_NAME


def get_table_counts(cursor):
    tables = ["trainer_sessions", "sale_items", "sales", "purchases", "payments", "memberships", "customers", "products"]
    counts = {}
    for table in tables:
        try:
            row = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        except sqlite3.OperationalError:
            counts[table] = 0
    return counts


def main():
    if not DB_PATH.exists():
        print(f"Database file not found: {DB_PATH}")
        return

    # 1. Safety backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = DB_PATH.with_name(f"{DB_NAME}.bak_{timestamp}")
    shutil.copy2(DB_PATH, backup_file)
    print(f"Safety backup created: {backup_file.name}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # 2. Print row counts before
    counts_before = get_table_counts(cur)
    print("\nCurrent Database State:")
    print(f"- trainer_sessions: {counts_before['trainer_sessions']} rows")
    print(f"- sale_items: {counts_before['sale_items']} rows")
    print(f"- sales: {counts_before['sales']} rows")
    print(f"- purchases: {counts_before['purchases']} rows")
    print(f"- payments: {counts_before['payments']} rows")
    print(f"- memberships: {counts_before['memberships']} rows")
    print(f"- customers: {counts_before['customers']} rows")
    print(f"- products (catalog): {counts_before['products']} rows (will be kept)")
    print()

    # 3. Exact confirmation
    confirmation = input("Enter 'DELETE ALL' to confirm (anything else to cancel): ").strip()
    if confirmation != "DELETE ALL":
        print("\nOperation cancelled. No changes made.")
        conn.close()
        return

    # 4. Single atomic transaction
    try:
        cur.execute("BEGIN TRANSACTION")
        cur.execute("DELETE FROM trainer_sessions")
        cur.execute("DELETE FROM sale_items")
        cur.execute("DELETE FROM sales")
        cur.execute("DELETE FROM purchases")
        cur.execute("DELETE FROM payments")
        cur.execute("DELETE FROM memberships")
        cur.execute("DELETE FROM customers")
        cur.execute("""
            DELETE FROM sqlite_sequence 
            WHERE name IN ('trainer_sessions', 'sale_items', 'sales', 'purchases', 'payments', 'memberships', 'customers')
        """)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"\nError during deletion: {e}. Transaction rolled back.")
        conn.close()
        return

    # 5. Print row counts after
    counts_after = get_table_counts(cur)
    print("\nDatabase State After Cleanup:")
    print(f"- trainer_sessions: {counts_after['trainer_sessions']} rows")
    print(f"- sale_items: {counts_after['sale_items']} rows")
    print(f"- sales: {counts_after['sales']} rows")
    print(f"- purchases: {counts_after['purchases']} rows")
    print(f"- payments: {counts_after['payments']} rows")
    print(f"- memberships: {counts_after['memberships']} rows")
    print(f"- customers: {counts_after['customers']} rows")
    print(f"- products (catalog): {counts_after['products']} rows")

    cleared = (
        counts_after['trainer_sessions'] == 0
        and counts_after['sale_items'] == 0
        and counts_after['sales'] == 0
        and counts_after['purchases'] == 0
        and counts_after['payments'] == 0
        and counts_after['memberships'] == 0
        and counts_after['customers'] == 0
    )

    if cleared:
        print("\nSuccess: All customer, membership, payment, purchase, and sale records deleted.")
        print("Autoincrement counters reset. The next customer will receive ID 1.")
    else:
        print("\nWarning: Cleanup incomplete. Please check database.")

    conn.close()


if __name__ == "__main__":
    main()
