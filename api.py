import calendar
import re

def add_one_year(start_dt: date) -> date:
    try:
        return start_dt.replace(year=start_dt.year + 1)
    except ValueError:
        return start_dt.replace(year=start_dt.year + 1, day=28)

def add_one_month(start_dt: date) -> date:
    year = start_dt.year
    month = start_dt.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(start_dt.day, max_day)
    return date(year, month, day)

from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Response
from database import connect, initialize_database
from models import (
    CATEGORY_TO_TYPE,
    Customer,
    Membership,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    SaleCreate,
    SaleLineItemCreate,
    SaleVoid,
    Trainer,
    TrainerSessionCreate,
)


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield


app = FastAPI(title="Gym Management API", lifespan=lifespan)


def rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


def require_record(db, table, record_id):
    allowed = {"customers", "memberships", "payments", "products", "sales", "trainers"}
    if table not in allowed:
        raise ValueError("Invalid table")

    row = db.execute(
        f"SELECT * FROM {table} WHERE id = ?", (record_id,)
    ).fetchone()

    if row is None:
        if table == "customers":
            raise HTTPException(404, f"Customer with ID {record_id} was not found.")
        singular = {"memberships": "membership", "payments": "payment", "products": "product", "sales": "sale", "trainers": "trainer"}[table]
        raise HTTPException(404, f"There is no {singular} record with ID {record_id} right now.")
    return dict(row)


def cents(amount):
    return int(amount * 100)


def money(value):
    if value is None:
        value = 0
    return f"{Decimal(value) / 100:.2f}"


def format_payments(records):
    for record in records:
        record["amount"] = money(record.pop("amount_cents"))
    return records


def format_products(records, db=None):
    for record in records:
        if "price_cents" in record:
            record["price"] = money(record.pop("price_cents"))
        if db is not None:
            has_purchases = bool(
                db.execute(
                    "SELECT 1 FROM purchases WHERE product_id=? LIMIT 1",
                    (record["id"],)
                ).fetchone()
                or db.execute(
                    "SELECT 1 FROM sale_items WHERE product_id=? LIMIT 1",
                    (record["id"],)
                ).fetchone()
            )
            record["has_purchases"] = has_purchases
            record["can_delete"] = not has_purchases
        else:
            record["can_delete"] = True
    return records


@app.get("/")
def home():
    return {"message": "Gym Management API is running"}


# CUSTOMERS

@app.post("/customers", status_code=201)
def create_customer(data: Customer):
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO customers(first_name, last_name, phone) VALUES (?, ?, ?)",
            (data.first_name, data.last_name, data.phone)
        )
        return {"id": cursor.lastrowid, **data.model_dump()}


def compute_customer_plan_status(mems, plan_name, today_str):
    if plan_name in ("Monthly session", "Member session, monthly"):
        plan_mems = [m for m in mems if m["plan"] in ("Monthly session", "Member session, monthly")]
    else:
        plan_mems = [m for m in mems if m["plan"] == plan_name]
    if not plan_mems:
        return "None", None, False

    active_mems = [m for m in plan_mems if m["start_date"] <= today_str <= m["end_date"]]
    future_mems = [m for m in plan_mems if m["start_date"] > today_str]
    past_mems = [m for m in plan_mems if m["end_date"] < today_str]

    has_waiting = len(future_mems) > 0

    if active_mems:
        latest_active = max(active_mems, key=lambda m: (m["end_date"], m["id"]))
        return "Active", latest_active["end_date"], has_waiting
    elif future_mems:
        latest_future = max(future_mems, key=lambda m: (m["end_date"], m["id"]))
        return "Upcoming", latest_future["end_date"], has_waiting
    else:
        latest_expired = max(past_mems, key=lambda m: (m["end_date"], m["id"]))
        return "Expired", latest_expired["end_date"], False


def enrich_customers(db, records):
    today = date.today().isoformat()
    for record in records:
        mems = rows(db.execute(
            """SELECT id, plan, start_date, end_date
               FROM memberships
               WHERE customer_id = ?
               ORDER BY start_date ASC, id ASC""",
            (record["id"],)
        ))
        y_status, y_end, y_waiting = compute_customer_plan_status(mems, "Yearly membership", today)
        m_status, m_end, m_waiting = compute_customer_plan_status(mems, "Member session, monthly", today)

        record["membership"] = y_status if y_status != "None" else None
        record["subscription"] = m_status if m_status != "None" else None

        record["yearly_status"] = y_status
        record["yearly_end_date"] = y_end
        record["yearly_has_waiting"] = y_waiting

        record["monthly_status"] = m_status
        record["monthly_end_date"] = m_end
        record["monthly_has_waiting"] = m_waiting

        # Register eligibility:
        record["can_register_yearly"] = (y_status == "None")
        record["can_register_monthly"] = (m_status == "None")

        # Renew eligibility:
        record["can_renew_yearly"] = (y_status in ("Active", "Expired") and not y_waiting)
        record["can_renew_monthly"] = (m_status in ("Active", "Expired") and not m_waiting)

        has_payments = bool(db.execute(
            "SELECT 1 FROM payments WHERE customer_id = ? LIMIT 1",
            (record["id"],)
        ).fetchone())
        record["has_history"] = bool(mems) or has_payments
        record["can_delete"] = not record["has_history"]

        # Backward compatibility aliases
        record["can_register"] = record["can_register_yearly"]
        record["can_renew"] = record["can_renew_yearly"]
        record["current_end_date"] = y_end or m_end

    return records


@app.get("/customers")
def list_customers(first_name: str = "", last_name: str = "", search: str = "", eligibility: str = ""):
    with connect() as db:
        if first_name and last_name:
            records = rows(db.execute(
                """SELECT * FROM customers
                   WHERE first_name = ? COLLATE NOCASE AND last_name = ? COLLATE NOCASE
                   ORDER BY id""",
                (first_name, last_name)
            ))
        elif search:
            records = rows(db.execute(
                """SELECT * FROM customers
                   WHERE first_name LIKE ? OR last_name LIKE ? OR phone LIKE ?
                   ORDER BY id""",
                (f"%{search}%", f"%{search}%", f"%{search}%")
            ))
        else:
            records = rows(db.execute("SELECT * FROM customers ORDER BY id"))
        enriched = enrich_customers(db, records)

        filter_map = {
            "register": "can_register_yearly",
            "register_yearly": "can_register_yearly",
            "register_monthly": "can_register_monthly",
            "renew": "can_renew_yearly",
            "renew_yearly": "can_renew_yearly",
            "renew_monthly": "can_renew_monthly",
            "delete": "can_delete",
        }
        if eligibility in filter_map:
            key = filter_map[eligibility]
            return [r for r in enriched if r.get(key)]
        return enriched


@app.get("/customers/exists")
def check_customers_exist(eligibility: str = ""):
    with connect() as db:
        if not eligibility:
            row = db.execute(
                "SELECT EXISTS (SELECT 1 FROM customers) AS has_records"
            ).fetchone()
            return {"exists": bool(row["has_records"])}
        else:
            records = rows(db.execute("SELECT * FROM customers ORDER BY id"))
            enriched = enrich_customers(db, records)
            filter_map = {
                "register": "can_register_yearly",
                "register_yearly": "can_register_yearly",
                "register_monthly": "can_register_monthly",
                "renew": "can_renew_yearly",
                "renew_yearly": "can_renew_yearly",
                "renew_monthly": "can_renew_monthly",
                "delete": "can_delete",
            }
            if eligibility in filter_map:
                key = filter_map[eligibility]
                return {"exists": any(r.get(key) for r in enriched)}
            return {"exists": bool(records)}


@app.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    with connect() as db:
        rec = require_record(db, "customers", customer_id)
        return enrich_customers(db, [rec])[0]


@app.put("/customers/{customer_id}")
def update_customer(customer_id: int, data: Customer):
    with connect() as db:
        require_record(db, "customers", customer_id)
        db.execute(
            "UPDATE customers SET first_name=?, last_name=?, phone=? WHERE id=?",
            (data.first_name, data.last_name, data.phone, customer_id)
        )
        return {"id": customer_id, **data.model_dump()}


@app.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: int):
    with connect() as db:
        require_record(db, "customers", customer_id)

        references = (
            db.execute(
                "SELECT 1 FROM memberships WHERE customer_id=? LIMIT 1",
                (customer_id,)
            ).fetchone()
            or db.execute(
                "SELECT 1 FROM payments WHERE customer_id=? LIMIT 1",
                (customer_id,)
            ).fetchone()
            or db.execute(
                "SELECT 1 FROM sales WHERE customer_id=? LIMIT 1",
                (customer_id,)
            ).fetchone()
        )

        if references:
            raise HTTPException(
                409, "This customer has memberships or payments and cannot be deleted."
            )

        db.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    return Response(status_code=204)


# MEMBERSHIPS

@app.get("/memberships/exists")
def check_memberships_exist():
    with connect() as db:
        row = db.execute(
            "SELECT EXISTS (SELECT 1 FROM memberships) AS has_records"
        ).fetchone()
        return {"exists": bool(row["has_records"])}

@app.post("/memberships", status_code=201)
def create_membership(data: Membership):
    if data.end_date < data.start_date:
        raise HTTPException(422, "End date must not precede start date")

    with connect() as db:
        require_record(db, "customers", data.customer_id)
        today_str = date.today().isoformat()

        if data.plan in ("Monthly session", "Member session, monthly"):
            existing_m = db.execute(
                """SELECT 1 FROM memberships
                   WHERE customer_id = ? AND plan IN ('Monthly session', 'Member session, monthly') LIMIT 1""",
                (data.customer_id,)
            ).fetchone()
            if existing_m:
                raise HTTPException(409, "Customer already has a monthly session record. Use renew instead.")
        else:
            # Yearly membership
            existing = db.execute(
                "SELECT 1 FROM memberships WHERE customer_id = ? AND plan = 'Yearly membership' LIMIT 1",
                (data.customer_id,)
            ).fetchone()
            if existing:
                raise HTTPException(409, "Customer already has a yearly membership. Use renew instead.")

        cursor = db.execute(
            """INSERT INTO memberships
               (customer_id, plan, start_date, end_date)
               VALUES (?, ?, ?, ?)""",
            (data.customer_id, data.plan,
             data.start_date.isoformat(), data.end_date.isoformat())
        )
        membership_id = cursor.lastrowid

        payment_id = None
        if data.method:
            method = "Cash" if data.method.lower().startswith("c") else "E-Wallet"
            price_cents = 120000 if data.plan in ("Monthly session", "Member session, monthly") else 30000
            p_cur = db.execute(
                """INSERT INTO payments
                   (customer_id, description, amount_cents, method)
                   VALUES (?, ?, ?, ?)""",
                (data.customer_id, f"Plan: {data.plan}", price_cents, method)
            )
            payment_id = p_cur.lastrowid

        return {
            "id": membership_id,
            "payment_id": payment_id,
            **data.model_dump(mode="json")
        }


@app.post("/memberships/renew", status_code=201)
def renew_membership_record(data: Membership):
    if data.end_date < data.start_date:
        raise HTTPException(422, "End date must not precede start date")

    with connect() as db:
        require_record(db, "customers", data.customer_id)
        today_str = date.today().isoformat()

        mems = rows(db.execute(
            """SELECT id, plan, start_date, end_date
               FROM memberships
               WHERE customer_id = ?
               ORDER BY start_date ASC, id ASC""",
            (data.customer_id,)
        ))

        if data.plan in ("Monthly session", "Member session, monthly"):
            plan_mems = [m for m in mems if m["plan"] in ("Monthly session", "Member session, monthly")]
        else:
            plan_mems = [m for m in mems if m["plan"] == data.plan]

        if not plan_mems:
            raise HTTPException(409, f"Customer has never had a {data.plan}. Use register instead.")

        has_waiting = any(m["start_date"] > today_str for m in plan_mems)
        if has_waiting:
            raise HTTPException(409, f"Customer already has a waiting renewal for {data.plan}.")

        cursor = db.execute(
            """INSERT INTO memberships
               (customer_id, plan, start_date, end_date)
               VALUES (?, ?, ?, ?)""",
            (data.customer_id, data.plan,
             data.start_date.isoformat(), data.end_date.isoformat())
        )
        membership_id = cursor.lastrowid

        payment_id = None
        if data.method:
            method = "Cash" if data.method.lower().startswith("c") else "E-Wallet"
            price_cents = 120000 if data.plan in ("Monthly session", "Member session, monthly") else 30000
            p_cur = db.execute(
                """INSERT INTO payments
                   (customer_id, description, amount_cents, method)
                   VALUES (?, ?, ?, ?)""",
                (data.customer_id, f"Plan Renewal: {data.plan}", price_cents, method)
            )
            payment_id = p_cur.lastrowid

        return {
            "id": membership_id,
            "payment_id": payment_id,
            **data.model_dump(mode="json")
        }


@app.get("/memberships")
def list_memberships(status: str = "all", plan: str = ""):
    status = status.strip().lower()
    if status not in ("all", "active", "expired", "upcoming"):
        raise HTTPException(422, "Invalid membership status")

    today = date.today().isoformat()

    with connect() as db:
        if plan:
            if plan.lower() in ("monthly session", "member session, monthly"):
                records = rows(db.execute("""
                    SELECT m.*, (c.first_name || ' ' || c.last_name) AS customer_name
                    FROM memberships m
                    JOIN customers c ON c.id = m.customer_id
                    WHERE m.plan IN ('Monthly session', 'Member session, monthly')
                    ORDER BY m.customer_id ASC, m.start_date ASC, m.id ASC
                """))
            else:
                records = rows(db.execute("""
                    SELECT m.*, (c.first_name || ' ' || c.last_name) AS customer_name
                    FROM memberships m
                    JOIN customers c ON c.id = m.customer_id
                    WHERE m.plan = ?
                    ORDER BY m.customer_id ASC, m.start_date ASC, m.id ASC
                """, (plan,)))
        else:
            records = rows(db.execute("""
                SELECT m.*, (c.first_name || ' ' || c.last_name) AS customer_name
                FROM memberships m
                JOIN customers c ON c.id = m.customer_id
                ORDER BY m.customer_id ASC,
                         CASE WHEN m.plan = 'Yearly membership' THEN 0 ELSE 1 END ASC,
                         m.start_date ASC,
                         m.id ASC
            """))

    for record in records:
        record["status"] = (
            "Active" if record["start_date"] <= today <= record["end_date"]
            else "Expired" if record["end_date"] < today
            else "Upcoming"
        )

    if status == "all":
        return records
    return [r for r in records if r["status"].lower() == status]


@app.put("/memberships/{membership_id}")
def renew_membership(membership_id: int, data: Membership):
    if data.end_date < data.start_date:
        raise HTTPException(422, "Invalid date range")

    with connect() as db:
        old = require_record(db, "memberships", membership_id)

        if old["customer_id"] != data.customer_id:
            raise HTTPException(422, "Customer ID cannot be changed")

        db.execute(
            """UPDATE memberships
               SET plan=?, start_date=?, end_date=?
               WHERE id=?""",
            (data.plan, data.start_date.isoformat(),
             data.end_date.isoformat(), membership_id)
        )

        return {"id": membership_id, **data.model_dump(mode="json")}


# PAYMENTS

@app.get("/payments/exists")
def check_payments_exist():
    with connect() as db:
        row = db.execute(
            "SELECT EXISTS (SELECT 1 FROM payments) AS has_records"
        ).fetchone()
        return {"exists": bool(row["has_records"])}

@app.post("/payments", status_code=201)
def create_payment(data: Payment):
    with connect() as db:
        require_record(db, "customers", data.customer_id)

        cursor = db.execute(
            """INSERT INTO payments
               (customer_id, description, amount_cents, method)
               VALUES (?, ?, ?, ?)""",
            (data.customer_id, data.description,
             cents(data.amount), data.method)
        )

        return {"id": cursor.lastrowid, **data.model_dump(mode="json")}


@app.get("/payments")
def list_payments(method: str = "", search: str = ""):
    if method.strip().lower() == "cash":
        method = "Cash"
    elif method.strip().lower() in ("e-wallet", "ewallet"):
        method = "E-Wallet"
    if method and method not in ("Cash", "E-Wallet"):
        raise HTTPException(422, "Invalid payment method")

    with connect() as db:
        records = rows(db.execute("""
            SELECT p.*, (c.first_name || ' ' || c.last_name) AS customer_name
            FROM payments p
            JOIN customers c ON c.id = p.customer_id
            WHERE (? = '' OR p.method = ?)
            ORDER BY p.id DESC
        """, (method, method)))

    formatted = format_payments(records)
    if search:
        s = search.strip().lower()
        c_match = re.match(r'^(?:c|cust|customer)\s*(\d+)$', s)
        if c_match:
            cid = int(c_match.group(1))
            return [p for p in formatted if p["customer_id"] == cid]
        elif s.isdigit():
            val = int(s)
            by_pid = [p for p in formatted if p["id"] == val]
            if by_pid:
                return by_pid
            return [p for p in formatted if p["customer_id"] == val]
        else:
            return [p for p in formatted if s in p.get("customer_name", "").lower() or s in p.get("description", "").lower()]
    return formatted


# PRODUCTS AND SERVICES

@app.post("/products", status_code=201)
def create_product(data: Product):
    item_type = CATEGORY_TO_TYPE[data.category]
    with connect() as db:
        cursor = db.execute(
            """INSERT INTO products(name, category, type, price_cents)
               VALUES (?, ?, ?, ?)""",
            (data.name, data.category, item_type, cents(data.price))
        )
        return {
            "id": cursor.lastrowid,
            "name": data.name,
            "category": data.category,
            "type": item_type,
            "price": money(cents(data.price)),
        }


@app.get("/products/exists")
def check_products_exist(eligibility: str = ""):
    with connect() as db:
        if eligibility == "delete":
            row = db.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM products p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM purchases pu WHERE pu.product_id = p.id
                    )
                ) AS has_records
            """).fetchone()
            return {"exists": bool(row["has_records"])}
        row = db.execute(
            "SELECT EXISTS (SELECT 1 FROM products) AS has_records"
        ).fetchone()
        return {"exists": bool(row["has_records"])}


@app.get("/products")
def list_products(type: str = "", eligibility: str = ""):
    if type.strip().lower() == "service":
        type = "Service"
    elif type.strip().lower() == "product":
        type = "Product"
    if type and type not in ("Service", "Product"):
        raise HTTPException(422, "Invalid item type")
    with connect() as db:
        if type:
            records = rows(db.execute("SELECT * FROM products WHERE type = ? ORDER BY id", (type,)))
        else:
            records = rows(db.execute("SELECT * FROM products ORDER BY id"))
        formatted = format_products(records, db=db)
        if eligibility == "delete":
            return [r for r in formatted if r.get("can_delete")]
        return formatted


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with connect() as db:
        rec = require_record(db, "products", product_id)
        return format_products([rec], db=db)[0]


@app.put("/products/{product_id}")
def update_product(product_id: int, data: Product):
    item_type = CATEGORY_TO_TYPE[data.category]
    with connect() as db:
        require_record(db, "products", product_id)
        db.execute(
            """UPDATE products
               SET name=?, category=?, type=?, price_cents=?
               WHERE id=?""",
            (data.name, data.category, item_type, cents(data.price), product_id)
        )
        return {
            "id": product_id,
            "name": data.name,
            "category": data.category,
            "type": item_type,
            "price": money(cents(data.price)),
        }


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    with connect() as db:
        require_record(db, "products", product_id)

        if db.execute(
            "SELECT 1 FROM purchases WHERE product_id=? LIMIT 1",
            (product_id,)
        ).fetchone():
            raise HTTPException(409, "This item has purchase history and cannot be deleted.")

        db.execute("DELETE FROM products WHERE id=?", (product_id,))
    return Response(status_code=204)


@app.post("/purchases", status_code=201)
def create_purchase(data: Purchase):
    with connect() as db:
        require_record(db, "customers", data.customer_id)

        items = data.items
        if not items:
            if not data.product_id or not data.quantity:
                raise HTTPException(422, "Either product_id and quantity or items list must be provided")
            items = [PurchaseItem(product_id=data.product_id, quantity=data.quantity)]

        total = 0
        resolved_items = []
        for it in items:
            prod = require_record(db, "products", it.product_id)
            if it.quantity <= 0:
                raise HTTPException(422, "Quantity must be positive")
            line_cents = prod["price_cents"] * it.quantity
            total += line_cents
            resolved_items.append((prod, it.quantity, line_cents))

        if total <= 0:
            raise HTTPException(422, "Purchase total must be positive")

        if len(resolved_items) == 1:
            prod, qty, _ = resolved_items[0]
            desc = f"{prod['name']} x{qty}"
        else:
            first_prod, first_qty, _ = resolved_items[0]
            desc = f"{first_prod['name']} x{first_qty} +{len(resolved_items) - 1} more"

        payment = db.execute(
            """INSERT INTO payments
               (customer_id, description, amount_cents, method)
               VALUES (?, ?, ?, ?)""",
            (data.customer_id, desc, total, data.method)
        )
        payment_id = payment.lastrowid

        first_purchase_id = None
        for prod, qty, _ in resolved_items:
            purchase = db.execute(
                """INSERT INTO purchases
                   (customer_id, product_id, quantity,
                    unit_price_cents, payment_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (data.customer_id, prod["id"], qty, prod["price_cents"], payment_id)
            )
            if first_purchase_id is None:
                first_purchase_id = purchase.lastrowid

        return {
            "id": first_purchase_id,
            "payment_id": payment_id,
            "total": money(total)
        }


# SALES

@app.post("/sales", status_code=201)
def create_sale(data: SaleCreate):
    today = date.today().isoformat()
    with connect() as db:
        customer_id = data.customer_id
        if customer_id is not None:
            cust = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not cust:
                raise HTTPException(404, f"Customer with ID {customer_id} was not found.")
            mems = rows(db.execute("SELECT * FROM memberships WHERE customer_id=? ORDER BY end_date ASC", (customer_id,)))
            y_status, _, _ = compute_customer_plan_status(mems, "Yearly membership", today)
            customer_type = "Member" if y_status == "Active" else "Non-member"
            customer_name = f"{cust['first_name']} {cust['last_name']}"
        else:
            customer_type = "Non-member"
            customer_name = "Walk-in"

        if not data.items:
            raise HTTPException(422, "Add at least one item first")

        total_cents = 0
        resolved_items = []
        for it in data.items:
            prod = db.execute("SELECT * FROM products WHERE id=?", (it.product_id,)).fetchone()
            if not prod or prod["is_active"] != 1:
                raise HTTPException(422, "Item not available for this customer")

            if prod["category"] == "Membership" or prod["name"] in ("Yearly membership", "Monthly session"):
                raise HTTPException(422, "Item not available for this customer")

            if prod["applies_to"] == "Members only" and customer_type != "Member":
                raise HTTPException(422, "Item not available for this customer")
            if prod["applies_to"] == "Non-members only" and customer_type == "Member":
                raise HTTPException(422, "Item not available for this customer")

            if it.quantity < 1 or it.quantity > 99:
                raise HTTPException(422, "Enter a quantity from 1 to 99")

            line_amount = prod["price_cents"] * it.quantity
            total_cents += line_amount
            resolved_items.append({
                "product_id": prod["id"],
                "item_name": prod["name"],
                "category": prod["category"],
                "unit_price_cents": prod["price_cents"],
                "quantity": it.quantity,
                "line_amount_cents": line_amount
            })

        tendered_cents = cents(data.amount_tendered)
        if data.payment_method == "Cash":
            if tendered_cents < total_cents:
                raise HTTPException(422, "Amount is less than the total due")
            change_cents = tendered_cents - total_cents
        else:
            tendered_cents = total_cents
            change_cents = 0

        last_id = db.execute("SELECT COALESCE(MAX(id), 0) FROM sales").fetchone()[0]
        receipt_no = f"R-{last_id + 1:06d}"

        cur = db.execute("""
            INSERT INTO sales (receipt_no, customer_id, customer_name, customer_type, total_cents,
                               payment_method, amount_tendered_cents, change_cents, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Completed')
        """, (receipt_no, customer_id, customer_name, customer_type, total_cents,
              data.payment_method, tendered_cents, change_cents))
        sale_id = cur.lastrowid

        for it in resolved_items:
            db.execute("""
                INSERT INTO sale_items (sale_id, product_id, item_name, category, unit_price_cents, quantity, line_amount_cents)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sale_id, it["product_id"], it["item_name"], it["category"], it["unit_price_cents"], it["quantity"], it["line_amount_cents"]))

        sale = dict(db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone())
        items = rows(db.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)))
        sale["total"] = money(sale.pop("total_cents"))
        sale["amount_tendered"] = money(sale.pop("amount_tendered_cents"))
        sale["change"] = money(sale.pop("change_cents"))
        for it in items:
            it["unit_price"] = money(it.pop("unit_price_cents"))
            it["line_amount"] = money(it.pop("line_amount_cents"))
        sale["items"] = items
        return sale


@app.get("/sales")
def list_sales(search: str = "", status: str = "", date: str = ""):
    query = "SELECT * FROM sales WHERE 1=1"
    params = []

    if status.strip():
        query += " AND status = ?"
        params.append(status.strip())

    if date.strip():
        query += " AND date(created_at) = date(?)"
        params.append(date.strip())

    if search.strip():
        s = f"%{search.strip()}%"
        query += " AND (receipt_no LIKE ? OR customer_name LIKE ? OR (customer_id IS NOT NULL AND customer_id = ?))"
        cid = int(search.strip()) if search.strip().isdigit() else -1
        params.extend([s, s, cid])

    query += " ORDER BY created_at DESC, id DESC"

    with connect() as db:
        records = rows(db.execute(query, params))
        for sale in records:
            sale_id = sale["id"]
            items = rows(db.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)))
            sale["total"] = money(sale.pop("total_cents"))
            sale["amount_tendered"] = money(sale.pop("amount_tendered_cents"))
            sale["change"] = money(sale.pop("change_cents"))
            for it in items:
                it["unit_price"] = money(it.pop("unit_price_cents"))
                it["line_amount"] = money(it.pop("line_amount_cents"))
            sale["items"] = items
        return records


@app.get("/sales/{sale_id}")
def get_sale(sale_id: int):
    with connect() as db:
        sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale:
            raise HTTPException(404, f"There is no sale record with ID {sale_id} right now.")
        sale = dict(sale)
        items = rows(db.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)))
        sale["total"] = money(sale.pop("total_cents"))
        sale["amount_tendered"] = money(sale.pop("amount_tendered_cents"))
        sale["change"] = money(sale.pop("change_cents"))
        for it in items:
            it["unit_price"] = money(it.pop("unit_price_cents"))
            it["line_amount"] = money(it.pop("line_amount_cents"))
        sale["items"] = items
        ts_row = db.execute("SELECT trainer_name, session_date_time FROM trainer_sessions WHERE sale_id=?", (sale_id,)).fetchone()
        if ts_row:
            sale["trainer_name"] = ts_row["trainer_name"]
            sale["session_date_time"] = ts_row["session_date_time"]
        return sale


@app.post("/sales/{sale_id}/void")
def void_sale_endpoint(sale_id: int, data: SaleVoid):
    reason = data.reason.strip()
    if not reason:
        raise HTTPException(422, "Void reason is required")
    with connect() as db:
        sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale:
            raise HTTPException(404, f"There is no sale record with ID {sale_id} right now.")
        if sale["status"] == "Voided":
            raise HTTPException(422, "Sale is already voided")
        db.execute(
            "UPDATE sales SET status='Voided', void_reason=?, voided_at=datetime('now', 'localtime') WHERE id=?",
            (reason, sale_id)
        )
        updated = dict(db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone())
        items = rows(db.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)))
        updated["total"] = money(updated.pop("total_cents"))
        updated["amount_tendered"] = money(updated.pop("amount_tendered_cents"))
        updated["change"] = money(updated.pop("change_cents"))
        for it in items:
            it["unit_price"] = money(it.pop("unit_price_cents"))
            it["line_amount"] = money(it.pop("line_amount_cents"))
        updated["items"] = items
        ts_row = db.execute("SELECT trainer_name, session_date_time FROM trainer_sessions WHERE sale_id=?", (sale_id,)).fetchone()
        if ts_row:
            updated["trainer_name"] = ts_row["trainer_name"]
            updated["session_date_time"] = ts_row["session_date_time"]
        return updated


# TRAINERS & TRAINER SESSIONS

@app.get("/trainers")
def list_trainers(status: str = "Active"):
    with connect() as db:
        if status.strip():
            return rows(db.execute("SELECT * FROM trainers WHERE status = ? ORDER BY id ASC", (status.strip(),)))
        return rows(db.execute("SELECT * FROM trainers ORDER BY id ASC"))


@app.get("/customers/{customer_id}/trainer-sessions/count-this-month")
def customer_trainer_sessions_count(customer_id: int):
    with connect() as db:
        require_record(db, "customers", customer_id)
        current_month = date.today().strftime("%Y-%m")
        count = db.execute("""
            SELECT COUNT(*) FROM trainer_sessions ts
            JOIN sales s ON s.id = ts.sale_id
            WHERE ts.customer_id = ?
              AND s.status = 'Completed'
              AND strftime('%Y-%m', ts.session_date_time) = ?
        """, (customer_id, current_month)).fetchone()[0]
        return {"customer_id": customer_id, "month": current_month, "count": count}


@app.post("/trainer-sessions", status_code=201)
def create_trainer_session(data: TrainerSessionCreate):
    today_str = date.today().isoformat()
    now_dt = datetime.now()

    if data.session_datetime:
        dt_str = data.session_datetime.strip()
        parsed_dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed_dt = datetime.strptime(dt_str, fmt)
                break
            except ValueError:
                pass
        if not parsed_dt:
            raise HTTPException(422, "Enter a valid date and time that is not in the future")
        if parsed_dt > now_dt:
            raise HTTPException(422, "Enter a valid date and time that is not in the future")
        formatted_session_dt = parsed_dt.strftime("%Y-%m-%d %H:%M")
    else:
        formatted_session_dt = now_dt.strftime("%Y-%m-%d %H:%M")

    with connect() as db:
        trainer = db.execute("SELECT * FROM trainers WHERE id=? AND status='Active'", (data.trainer_id,)).fetchone()
        if not trainer:
            raise HTTPException(422, "Invalid choice")

        if data.customer_id is not None:
            cust = db.execute("SELECT * FROM customers WHERE id=?", (data.customer_id,)).fetchone()
            if not cust:
                raise HTTPException(404, f"Customer with ID {data.customer_id} was not found.")
            mems = rows(db.execute("SELECT * FROM memberships WHERE customer_id=? ORDER BY end_date ASC", (data.customer_id,)))
            y_status, _, _ = compute_customer_plan_status(mems, "Yearly membership", today_str)
            customer_type = "Member" if y_status == "Active" else "Non-member"
            customer_name = f"{cust['first_name']} {cust['last_name']}"
        else:
            customer_type = "Non-member"
            customer_name = "Walk-in"

        prod = db.execute("SELECT * FROM products WHERE id=?", (data.product_id,)).fetchone()
        if not prod or prod["is_active"] != 1 or prod["category"] != "Coaching":
            raise HTTPException(422, "Session type not available for this customer")

        if prod["applies_to"] == "Members only" and customer_type != "Member":
            raise HTTPException(422, "Session type not available for this customer")
        if prod["applies_to"] == "Non-members only" and customer_type == "Member":
            raise HTTPException(422, "Session type not available for this customer")

        price_cents = prod["price_cents"]
        tendered_cents = cents(data.amount_tendered)

        if data.payment_method == "Cash":
            if tendered_cents < price_cents:
                raise HTTPException(422, "Amount is less than the total due")
            change_cents = tendered_cents - price_cents
        else:
            tendered_cents = price_cents
            change_cents = 0

        last_id = db.execute("SELECT COALESCE(MAX(id), 0) FROM sales").fetchone()[0]
        receipt_no = f"R-{last_id + 1:06d}"

        cur = db.execute("""
            INSERT INTO sales (receipt_no, customer_id, customer_name, customer_type, total_cents,
                               payment_method, amount_tendered_cents, change_cents, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Completed')
        """, (receipt_no, data.customer_id, customer_name, customer_type, price_cents,
              data.payment_method, tendered_cents, change_cents))
        sale_id = cur.lastrowid

        db.execute("""
            INSERT INTO sale_items (sale_id, product_id, item_name, category, unit_price_cents, quantity, line_amount_cents)
            VALUES (?, ?, ?, 'Coaching', ?, 1, ?)
        """, (sale_id, prod["id"], prod["name"], price_cents, price_cents))

        cur_ts = db.execute("""
            INSERT INTO trainer_sessions (sale_id, customer_id, customer_name, product_id, trainer_id, trainer_name, session_date_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sale_id, data.customer_id, customer_name, prod["id"], trainer["id"], trainer["name"], formatted_session_dt))
        ts_id = cur_ts.lastrowid

        return {
            "session_id": ts_id,
            "sale_id": sale_id,
            "receipt_no": receipt_no,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "customer_id": data.customer_id,
            "customer_name": customer_name,
            "customer_type": customer_type,
            "session_type": prod["name"],
            "trainer_id": trainer["id"],
            "trainer_name": trainer["name"],
            "session_date_time": formatted_session_dt,
            "total": money(price_cents),
            "payment_method": data.payment_method,
            "amount_tendered": money(tendered_cents),
            "change": money(change_cents),
        }


# REPORTS

@app.get("/reports/sales")
def sales_report(period: str = "daily"):
    period = period.strip().lower()
    if period not in ("daily", "monthly"):
        raise HTTPException(422, "Period must be daily or monthly")

    grouping = "%Y-%m-%d" if period == "daily" else "%Y-%m"

    with connect() as db:
        periods = [
            r[0] for r in db.execute(f"""
                SELECT DISTINCT p FROM (
                    SELECT strftime('{grouping}', created_at) AS p FROM payments
                    UNION
                    SELECT strftime('{grouping}', created_at) AS p FROM sales
                ) WHERE p IS NOT NULL ORDER BY p DESC
            """).fetchall()
        ]

        STANDARD_CATEGORIES = ["Membership", "Gym Access", "Coaching", "Beverage", "Supplement", "Merchandise"]
        records = []

        for p in periods:
            mem_row = db.execute(f"""
                SELECT COUNT(*) AS count, COALESCE(SUM(amount_cents), 0) AS cents
                FROM payments
                WHERE strftime('{grouping}', created_at) = ?
            """, (p,)).fetchone()
            mem_cents = mem_row["cents"] or 0
            mem_tx = mem_row["count"] or 0

            cat_rows = db.execute(f"""
                SELECT si.category,
                       COUNT(DISTINCT s.id) AS tx,
                       COALESCE(SUM(si.line_amount_cents), 0) AS total_cents
                FROM sale_items si
                JOIN sales s ON s.id = si.sale_id
                WHERE s.status = 'Completed' AND strftime('{grouping}', s.created_at) = ?
                GROUP BY si.category
            """, (p,)).fetchall()
            cat_map = {r["category"]: {"tx": r["tx"], "cents": r["total_cents"]} for r in cat_rows}

            sales_row = db.execute(f"""
                SELECT COUNT(*) AS count, COALESCE(SUM(total_cents), 0) AS cents
                FROM sales
                WHERE status = 'Completed' AND strftime('{grouping}', created_at) = ?
            """, (p,)).fetchone()
            sales_cents = sales_row["cents"] or 0
            sales_tx = sales_row["count"] or 0

            voided_count = db.execute(f"""
                SELECT COUNT(*) FROM sales
                WHERE status = 'Voided' AND strftime('{grouping}', created_at) = ?
            """, (p,)).fetchone()[0]

            categories = []
            for cat in STANDARD_CATEGORIES:
                c_cents = 0
                c_tx = 0
                if cat == "Membership":
                    c_cents = mem_cents + cat_map.get("Membership", {}).get("cents", 0)
                    c_tx = mem_tx + cat_map.get("Membership", {}).get("tx", 0)
                else:
                    c_cents = cat_map.get(cat, {}).get("cents", 0)
                    c_tx = cat_map.get(cat, {}).get("tx", 0)
                if c_cents > 0 or c_tx > 0:
                    categories.append({
                        "category": cat,
                        "transactions": c_tx,
                        "amount": money(c_cents)
                    })

            tx_list = []
            if period == "daily":
                sale_txs = db.execute("""
                    SELECT receipt_no, created_at, customer_name, total_cents, status
                    FROM sales
                    WHERE strftime('%Y-%m-%d', created_at) = ?
                    ORDER BY created_at DESC, id DESC
                """, (p,)).fetchall()
                for s in sale_txs:
                    time_str = s["created_at"][11:16] if len(s["created_at"]) >= 16 else s["created_at"]
                    tx_list.append({
                        "receipt_no": s["receipt_no"],
                        "time": time_str,
                        "customer": s["customer_name"],
                        "total": money(s["total_cents"]),
                        "status": s["status"]
                    })
                mem_txs = db.execute("""
                    SELECT p.id, p.created_at, p.amount_cents,
                           c.first_name || ' ' || c.last_name AS customer_name
                    FROM payments p
                    JOIN customers c ON c.id = p.customer_id
                    WHERE strftime('%Y-%m-%d', p.created_at) = ?
                    ORDER BY p.created_at DESC, p.id DESC
                """, (p,)).fetchall()
                for m in mem_txs:
                    time_str = m["created_at"][11:16] if len(m["created_at"]) >= 16 else m["created_at"]
                    tx_list.append({
                        "receipt_no": f"PAY-{m['id']:04d}",
                        "time": time_str,
                        "customer": m["customer_name"],
                        "total": money(m["amount_cents"]),
                        "status": "Completed"
                    })
                tx_list.sort(key=lambda x: x["time"], reverse=True)

            total_tx = mem_tx + sales_tx
            total_cents = mem_cents + sales_cents

            prod_cents = sum(cat_map.get(c, {}).get("cents", 0) for c in ["Beverage", "Supplement", "Merchandise"])
            serv_cents = total_cents - prod_cents
            prod_tx = sum(cat_map.get(c, {}).get("tx", 0) for c in ["Beverage", "Supplement", "Merchandise"])
            serv_tx = total_tx - prod_tx

            records.append({
                "period": p,
                "categories": categories,
                "total_transactions": total_tx,
                "total_sales": money(total_cents),
                "voided_count": voided_count,
                "transactions": tx_list,
                "service_income": money(serv_cents),
                "product_income": money(prod_cents),
                "service_transactions": serv_tx,
                "product_transactions": prod_tx,
                "total": money(total_cents)
            })

        return records


@app.get("/reports/payment-methods")
def payment_methods_report():
    with connect() as db:
        records = rows(db.execute("""
            SELECT method, COUNT(*) AS transactions,
                   SUM(amount_cents) AS total_cents
            FROM payments GROUP BY method
        """))

    for record in records:
        record["total"] = money(record.pop("total_cents"))
    return records


@app.get("/reports/memberships")
def membership_report():
    memberships = list_memberships()
    yearly = [m for m in memberships if m["plan"] == "Yearly membership"]
    monthly = [m for m in memberships if m["plan"] == "Member session, monthly"]
    return {
        "yearly": {
            "active": sum(m["status"] == "Active" for m in yearly),
            "expired": sum(m["status"] == "Expired" for m in yearly),
            "upcoming": sum(m["status"] == "Upcoming" for m in yearly),
            "total": len(yearly)
        },
        "monthly": {
            "active": sum(m["status"] == "Active" for m in monthly),
            "expired": sum(m["status"] == "Expired" for m in monthly),
            "upcoming": sum(m["status"] == "Upcoming" for m in monthly),
            "total": len(monthly)
        },
        "active": sum(m["status"] == "Active" for m in memberships),
        "expired": sum(m["status"] == "Expired" for m in memberships),
        "upcoming": sum(m["status"] == "Upcoming" for m in memberships),
        "total": len(memberships)
    }
