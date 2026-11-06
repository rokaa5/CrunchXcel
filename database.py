import sqlite3
from pathlib import Path
from contextlib import contextmanager

import os
DB_NAME = os.environ.get("GYM_DB_NAME", "gym.db")
DB_PATH = Path(__file__).resolve().parent / DB_NAME

CATEGORY_TO_TYPE = {
    "Membership": "Service",
    "Gym Access": "Service",
    "Coaching": "Service",
    "Beverage": "Product",
    "Supplement": "Product",
    "Merchandise": "Product",
}

DEFAULT_PRODUCTS = [
    # Membership and Gym Access (Services: IDs 1 to 4)
    ("Yearly membership", "Membership", "Service", 30000, "Anyone", 1),
    ("Member session, daily", "Gym Access", "Service", 5000, "Members only", 1),
    ("Monthly session", "Gym Access", "Service", 120000, "Anyone", 1),
    ("Walk-in non-member, daily", "Gym Access", "Service", 7000, "Non-members only", 1),
    # Personal Trainer (Services: IDs 5 to 7)
    ("Personal trainer, member, daily session", "Coaching", "Service", 12000, "Members only", 1),
    ("Personal trainer, member, per session (monthly basis)", "Coaching", "Service", 7000, "Members only", 1),
    ("Personal trainer, non-member", "Coaching", "Service", 14000, "Non-members only", 1),
    # Drinks (Products: IDs 8 to 13)
    ("Bottled water", "Beverage", "Product", 1000, "Anyone", 1),
    ("Cobra", "Beverage", "Product", 2500, "Anyone", 1),
    ("Sting", "Beverage", "Product", 2500, "Anyone", 1),
    ("Vitamilk", "Beverage", "Product", 3500, "Anyone", 1),
    ("Gatorade", "Beverage", "Product", 4000, "Anyone", 1),
    ("Fit N Right Pineapple", "Beverage", "Product", 4000, "Anyone", 1),
    # Supplements (Products: IDs 14 to 18)
    ("Optimum Nutrition Micronized Creatine Powder, 300 g (60 servings)", "Supplement", "Product", 184500, "Anyone", 1),
    ("ProtHN Monohydrate Creatine Powder, 60 servings", "Supplement", "Product", 120000, "Anyone", 1),
    ("Optimum Nutrition Superior Amino 2222, 160 tablets", "Supplement", "Product", 190000, "Anyone", 1),
    ("ProtHN Whey Protein, box", "Supplement", "Product", 180000, "Anyone", 1),
    ("Mass gainer, bag", "Supplement", "Product", 250000, "Anyone", 1),
    # Merchandise (Products: ID 19)
    ("Insulated tumbler (white, pink, or blue)", "Merchandise", "Product", 65000, "Anyone", 1),
]


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def migrate_customers_table(db):
    cols = [r[1] for r in db.execute("PRAGMA table_info(customers)").fetchall()]
    if "name" in cols and "first_name" not in cols:
        db.execute("ALTER TABLE customers ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE customers ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
        rows = db.execute("SELECT id, name FROM customers").fetchall()
        for r in rows:
            parts = r["name"].strip().split(" ", 1)
            fname = parts[0]
            lname = parts[1] if len(parts) > 1 else ""
            db.execute(
                "UPDATE customers SET first_name=?, last_name=? WHERE id=?",
                (fname, lname, r["id"])
            )
        db.execute("ALTER TABLE customers DROP COLUMN name")


def migrate_products_table(db):
    cols = [r[1] for r in db.execute("PRAGMA table_info(products)").fetchall()]
    if "type" not in cols:
        db.execute(
            "ALTER TABLE products ADD COLUMN type TEXT NOT NULL DEFAULT 'Product' CHECK(type IN ('Service', 'Product'))"
        )
    if "applies_to" not in cols:
        db.execute(
            "ALTER TABLE products ADD COLUMN applies_to TEXT NOT NULL DEFAULT 'Anyone' CHECK(applies_to IN ('Anyone', 'Members only', 'Non-members only'))"
        )
    if "is_active" not in cols:
        db.execute(
            "ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))"
        )

    rows = db.execute("SELECT id, category, type FROM products").fetchall()
    for r in rows:
        mapped_type = CATEGORY_TO_TYPE.get(r["category"], "Service" if r["category"] == "Service" else "Product")
        if r["type"] != mapped_type:
            db.execute("UPDATE products SET type=? WHERE id=?", (mapped_type, r["id"]))
    db.execute("UPDATE products SET name='Monthly session' WHERE id=3")
    db.execute("UPDATE products SET name='Personal trainer, member, per session (monthly basis)' WHERE id=6")

    db.execute("UPDATE products SET applies_to='Members only' WHERE id IN (2, 5, 6)")
    db.execute("UPDATE products SET applies_to='Non-members only' WHERE id IN (4, 7)")
    db.execute("UPDATE products SET applies_to='Anyone' WHERE id NOT IN (2, 4, 5, 6, 7)")


def seed_default_products(db):
    count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        db.executemany(
            "INSERT INTO products (name, category, type, price_cents, applies_to, is_active) VALUES (?, ?, ?, ?, ?, ?)",
            DEFAULT_PRODUCTS
        )


def seed_default_trainers(db):
    count = db.execute("SELECT COUNT(*) FROM trainers").fetchone()[0]
    if count == 0:
        db.executemany(
            "INSERT INTO trainers (name, status) VALUES (?, ?)",
            [("Coach Alex", "Active"), ("Coach Mark", "Active")]
        )


def add_column_if_missing(db, table, column, definition):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_sales_and_memberships(db):
    """Add pricing, discount, idempotency, and membership-link columns without touching old rows."""
    add_column_if_missing(db, "sales", "subtotal_cents", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(db, "sales", "discount_cents", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(db, "sales", "membership_status", "TEXT")
    add_column_if_missing(db, "sales", "request_id", "TEXT")
    add_column_if_missing(db, "sales", "kind", "TEXT NOT NULL DEFAULT 'Product'")
    db.execute("UPDATE sales SET subtotal_cents = total_cents WHERE subtotal_cents = 0")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_request_id ON sales(request_id)")

    add_column_if_missing(db, "sale_items", "discount_cents", "INTEGER NOT NULL DEFAULT 0")

    add_column_if_missing(db, "memberships", "sale_id", "INTEGER")
    add_column_if_missing(db, "memberships", "amount_cents", "INTEGER")
    add_column_if_missing(db, "memberships", "created_at", "TEXT")
    add_column_if_missing(db, "memberships", "cancelled_at", "TEXT")


def backfill_membership_payments(db):
    """Link legacy memberships to the payment recorded with them, when the match is unambiguous."""
    groups = db.execute(
        """SELECT DISTINCT customer_id, plan FROM memberships
           WHERE sale_id IS NULL AND amount_cents IS NULL"""
    ).fetchall()
    for g in groups:
        mems = db.execute(
            """SELECT id FROM memberships
               WHERE customer_id=? AND plan=? AND sale_id IS NULL AND amount_cents IS NULL
               ORDER BY id""",
            (g["customer_id"], g["plan"])
        ).fetchall()
        pays = db.execute(
            """SELECT amount_cents, created_at FROM payments
               WHERE customer_id=? AND (description=? OR description=?)
               ORDER BY id""",
            (g["customer_id"], f"Plan: {g['plan']}", f"Plan Renewal: {g['plan']}")
        ).fetchall()
        if len(mems) == len(pays):
            for m, p in zip(mems, pays):
                db.execute(
                    "UPDATE memberships SET amount_cents=?, created_at=? WHERE id=?",
                    (p["amount_cents"], p["created_at"], m["id"])
                )


def ensure_daily_session_product(db):
    """Daily gym access has its own menu. Hide the two old catalog items and add one standard item.

    Old items are deactivated (not deleted) so existing purchases and receipts keep their references.
    """
    db.execute(
        "UPDATE products SET is_active = 0 WHERE name IN ('Member session, daily', 'Walk-in non-member, daily')"
    )
    exists = db.execute("SELECT 1 FROM products WHERE name = 'Daily session'").fetchone()
    if not exists:
        db.execute(
            """INSERT INTO products (name, category, type, price_cents, applies_to, is_active)
               VALUES ('Daily session', 'Gym Access', 'Service', 7000, 'Anyone', 1)"""
        )


def seed_default_discount_rules(db):
    """Seed the daily member price without overriding any existing configured discounts."""
    daily = db.execute("SELECT id FROM products WHERE name = 'Daily session'").fetchone()
    if not daily:
        return
    existing = db.execute(
        "SELECT 1 FROM discount_rules WHERE product_id = ? AND membership_type = 'Yearly' LIMIT 1",
        (daily["id"],),
    ).fetchone()
    if not existing:
        db.execute(
            """INSERT INTO discount_rules (product_id, membership_type, discount_type, value, is_active)
               VALUES (?, 'Yearly', 'fixed', 2000, 1)""",
            (daily["id"],),
        )


def initialize_database():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            method TEXT NOT NULL CHECK(method IN ('Cash', 'E-Wallet')),
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('Service', 'Product')),
            price_cents INTEGER NOT NULL CHECK(price_cents > 0),
            applies_to TEXT NOT NULL DEFAULT 'Anyone' CHECK(applies_to IN ('Anyone', 'Members only', 'Non-members only')),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price_cents INTEGER NOT NULL,
            payment_id INTEGER NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(payment_id) REFERENCES payments(id)
        );

        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_no TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            customer_id INTEGER,
            customer_name TEXT NOT NULL,
            customer_type TEXT NOT NULL CHECK(customer_type IN ('Member', 'Non-member')),
            total_cents INTEGER NOT NULL CHECK(total_cents > 0),
            payment_method TEXT NOT NULL CHECK(payment_method IN ('Cash', 'E-Wallet')),
            amount_tendered_cents INTEGER NOT NULL,
            change_cents INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Completed' CHECK(status IN ('Completed', 'Voided')),
            void_reason TEXT,
            voided_at TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit_price_cents INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 1 AND quantity <= 99),
            line_amount_cents INTEGER NOT NULL,
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS trainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive'))
        );

        CREATE TABLE IF NOT EXISTS trainer_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            customer_id INTEGER,
            customer_name TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            trainer_id INTEGER NOT NULL,
            trainer_name TEXT NOT NULL,
            session_date_time TEXT NOT NULL,
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(trainer_id) REFERENCES trainers(id)
        );

        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            check_in_at TEXT NOT NULL,
            used TEXT NOT NULL,
            sale_id INTEGER,
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(sale_id) REFERENCES sales(id)
        );

        CREATE TABLE IF NOT EXISTS refunds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL UNIQUE,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            method TEXT NOT NULL CHECK(method IN ('Cash', 'E-Wallet')),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(sale_id) REFERENCES sales(id)
        );

        CREATE INDEX IF NOT EXISTS idx_refunds_created_at ON refunds(created_at);

        CREATE TABLE IF NOT EXISTS discount_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            membership_type TEXT NOT NULL CHECK(membership_type IN ('Yearly', 'Monthly')),
            discount_type TEXT NOT NULL CHECK(discount_type IN ('percent', 'fixed')),
            value INTEGER NOT NULL CHECK(value > 0),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        """)
        migrate_customers_table(db)
        migrate_products_table(db)
        migrate_sales_and_memberships(db)
        add_column_if_missing(db, "trainer_sessions", "session_label", "TEXT")
        add_column_if_missing(db, "trainer_sessions", "cancelled_at", "TEXT")
        db.execute("""CREATE TABLE IF NOT EXISTS app_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'staff'))
        )""")
        from auth_utils import hash_password
        for username, role in (("admin", "admin"), ("staff", "staff")):
            existing = db.execute("SELECT 1 FROM app_users WHERE username = ?", (username,)).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO app_users(username, password_hash, role) VALUES (?, ?, ?)",
                    (username, hash_password(username), role)
                )
        seed_default_products(db)
        ensure_daily_session_product(db)
        seed_default_trainers(db)
        seed_default_discount_rules(db)
        backfill_membership_payments(db)
