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
    DailySessionCreate,
    QuoteRequest,
    ph_now,
    ph_today,
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


YEARLY_PLAN = "Yearly membership"
MONTHLY_PLAN = "Monthly session"
MONTHLY_PLAN_NAMES = ("Monthly session", "Member session, monthly")
DAILY_PRODUCT_NAME = "Daily session"

# Plans that already cover every daily visit while they are valid.
# Yearly membership is a membership fee (member rates), not free daily access.
GYM_ACCESS_PLANS = ("Monthly",)

STATUS_LABELS = {
    "Active": "Active",
    "Expired": "Expired",
    "Upcoming": "Not Yet Active",
    "None": "Not Registered",
}


def plan_label(status, has_cancelled=False):
    if status == "None" and has_cancelled:
        return "Cancelled"
    return STATUS_LABELS.get(status, status)


def canonical_plan(plan):
    if plan == YEARLY_PLAN:
        return YEARLY_PLAN
    if plan in MONTHLY_PLAN_NAMES:
        return MONTHLY_PLAN
    return None


def membership_summary(db, customer_id):
    """Current status of both plans, from the customer's records. Cancelled records are ignored."""
    today = ph_today().isoformat()
    all_mems = rows(db.execute(
        """SELECT id, plan, start_date, end_date, cancelled_at
           FROM memberships WHERE customer_id = ?
           ORDER BY start_date ASC, id ASC""",
        (customer_id,)
    ))
    mems = [m for m in all_mems if not m["cancelled_at"]]
    y_status, y_end, y_waiting = compute_customer_plan_status(mems, YEARLY_PLAN, today)
    m_status, m_end, m_waiting = compute_customer_plan_status(mems, MONTHLY_PLAN, today)
    y_cancelled = any(m["cancelled_at"] and m["plan"] == YEARLY_PLAN for m in all_mems)
    m_cancelled = any(m["cancelled_at"] and m["plan"] in MONTHLY_PLAN_NAMES for m in all_mems)
    qualifying = set()
    if y_status == "Active":
        qualifying.add("Yearly")
    if m_status == "Active":
        qualifying.add("Monthly")
    return {
        "yearly_status": y_status,
        "yearly_end_date": y_end,
        "yearly_has_waiting": y_waiting,
        "yearly_label": plan_label(y_status, y_cancelled),
        "monthly_status": m_status,
        "monthly_end_date": m_end,
        "monthly_has_waiting": m_waiting,
        "monthly_label": plan_label(m_status, m_cancelled),
        "qualifying_types": sorted(qualifying),
        "has_gym_access": any(t in GYM_ACCESS_PLANS for t in qualifying),
    }


def calculate_discounts(db, customer_id, items):
    """
    items: iterable of objects or dicts with product_id, quantity
    returns dict with customer details, membership summary, enriched items,
    subtotal_cents, discount_cents, total_cents
    """
    if customer_id is not None:
        cust = db.execute("SELECT id, first_name, last_name, phone FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not cust:
            raise HTTPException(404, f"Customer with ID {customer_id} was not found.")
        customer_name = f"{cust['first_name']} {cust['last_name']}".strip()
        mem_sum = membership_summary(db, customer_id)
        if mem_sum["yearly_status"] == "Active" or mem_sum["monthly_status"] == "Active":
            membership_status = "Active"
        elif mem_sum["yearly_status"] == "Upcoming" or mem_sum["monthly_status"] == "Upcoming":
            membership_status = "Not Yet Active"
        elif mem_sum["yearly_label"] == "Cancelled" or mem_sum["monthly_label"] == "Cancelled":
            membership_status = "Cancelled"
        elif mem_sum["yearly_status"] == "Expired" or mem_sum["monthly_status"] == "Expired":
            membership_status = "Expired"
        else:
            membership_status = "Not Registered"
    else:
        customer_name = "Walk-in"
        membership_status = "Not Registered"
        mem_sum = {
            "yearly_status": "None",
            "yearly_end_date": None,
            "yearly_has_waiting": False,
            "yearly_label": "Not Registered",
            "monthly_status": "None",
            "monthly_end_date": None,
            "monthly_has_waiting": False,
            "monthly_label": "Not Registered",
            "qualifying_types": [],
            "has_gym_access": False,
        }

    qualifying_set = set(mem_sum["qualifying_types"])
    enriched_items = []
    total_subtotal_cents = 0
    total_discount_cents = 0

    for item in items:
        pid = getattr(item, "product_id", None) if not isinstance(item, dict) else item.get("product_id")
        qty = getattr(item, "quantity", None) if not isinstance(item, dict) else item.get("quantity")
        if qty is None or qty < 1:
            qty = 1

        p = db.execute("SELECT id, name, category, price_cents, is_active FROM products WHERE id = ?", (pid,)).fetchone()
        if not p or p["is_active"] != 1:
            raise HTTPException(422, f"Item with ID {pid} is not available")

        unit_price_cents = p["price_cents"]

        rules = rows(db.execute(
            "SELECT membership_type, discount_type, value FROM discount_rules WHERE product_id = ? AND is_active = 1",
            (pid,)
        ))
        best_disc_unit = 0
        for r in rules:
            if r["membership_type"] in qualifying_set:
                dtype = r["discount_type"].lower()
                val = r["value"]
                if dtype == "fixed":
                    cand = min(unit_price_cents, val)
                elif dtype in ("percent", "percentage"):
                    cand = int(round(unit_price_cents * (val / 100.0)))
                else:
                    cand = 0
                if cand > best_disc_unit:
                    best_disc_unit = cand

        final_unit_price = unit_price_cents - best_disc_unit
        subtotal_cents = unit_price_cents * qty
        discount_cents = best_disc_unit * qty
        line_total_cents = subtotal_cents - discount_cents

        total_subtotal_cents += subtotal_cents
        total_discount_cents += discount_cents

        enriched_items.append({
            "product_id": p["id"],
            "name": p["name"],
            "item_name": p["name"],
            "category": p["category"],
            "quantity": qty,
            "unit_price_cents": unit_price_cents,
            "unit_price": money(unit_price_cents),
            "discount_unit_cents": best_disc_unit,
            "discount_unit": money(best_disc_unit),
            "final_unit_price_cents": final_unit_price,
            "final_unit_price": money(final_unit_price),
            "subtotal_cents": subtotal_cents,
            "subtotal": money(subtotal_cents),
            "discount_cents": discount_cents,
            "discount": money(discount_cents),
            "total_cents": line_total_cents,
            "total": money(line_total_cents),
        })

    final_total_cents = total_subtotal_cents - total_discount_cents
    return {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "membership_status": membership_status,
        "mem_sum": mem_sum,
        "items": enriched_items,
        "subtotal_cents": total_subtotal_cents,
        "discount_cents": total_discount_cents,
        "total_cents": final_total_cents,
    }


def enrich_customers(db, records):
    today = ph_today().isoformat()
    for record in records:
        mems = rows(db.execute(
            """SELECT id, plan, start_date, end_date
               FROM memberships
               WHERE customer_id = ? AND cancelled_at IS NULL
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

        last_visit = db.execute(
            """SELECT MAX(v.check_in_at) FROM visits v
               LEFT JOIN sales s ON s.id = v.sale_id
               WHERE v.customer_id = ? AND (s.id IS NULL OR s.status = 'Completed')""",
            (record["id"],)
        ).fetchone()[0]
        record["last_visit"] = last_visit[:10] if last_visit else None

        # Register eligibility:
        record["can_register_yearly"] = (y_status == "None")
        record["can_register_monthly"] = (m_status == "None")

        # Renew eligibility:
        record["can_renew_yearly"] = (y_status in ("Active", "Expired") and not y_waiting)
        record["can_renew_monthly"] = (m_status in ("Active", "Expired") and not m_waiting)

        # An active yearly membership qualifies for member-specific rates.
        record["is_active_yearly"] = (y_status == "Active")

        has_payments = bool(db.execute(
            "SELECT 1 FROM payments WHERE customer_id = ? LIMIT 1",
            (record["id"],)
        ).fetchone())
        has_sales = bool(db.execute(
            "SELECT 1 FROM sales WHERE customer_id = ? LIMIT 1",
            (record["id"],)
        ).fetchone())
        has_any_membership = bool(db.execute(
            "SELECT 1 FROM memberships WHERE customer_id = ? LIMIT 1",
            (record["id"],)
        ).fetchone())
        record["has_history"] = has_any_membership or has_payments or has_sales
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
            s_clean = search.strip()
            if s_clean.isdigit():
                records = rows(db.execute(
                    """SELECT * FROM customers
                       WHERE id = ? OR first_name LIKE ? OR last_name LIKE ? OR phone LIKE ?
                       ORDER BY id""",
                    (int(s_clean), f"%{search}%", f"%{search}%", f"%{search}%")
                ))
            else:
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
            "active_yearly": "is_active_yearly",
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
                "active_yearly": "is_active_yearly",
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


@app.get("/customers/{customer_id}/overview")
def get_customer_overview(customer_id: int):
    with connect() as db:
        cust = require_record(db, "customers", customer_id)
        today = ph_today().isoformat()
        mem_sum = membership_summary(db, customer_id)

        today_visit = db.execute(
            "SELECT id FROM visits WHERE customer_id = ? AND date(check_in_at) = ? LIMIT 1",
            (customer_id, today)
        ).fetchone()
        if today_visit:
            daily_access = "Active (Today)"
        elif mem_sum["has_gym_access"]:
            daily_access = "Active (Monthly Plan)"
        else:
            daily_access = "None"

        if "Yearly" in mem_sum["qualifying_types"]:
            discount_eligibility = "Yearly Member Rate (₱20.00 off daily)"
        else:
            discount_eligibility = "Standard / None"

        total_purchases = db.execute(
            "SELECT COUNT(*) FROM sales WHERE customer_id = ? AND status = 'Completed'",
            (customer_id,)
        ).fetchone()[0]

        sales_cents = db.execute(
            "SELECT COALESCE(SUM(total_cents), 0) FROM sales WHERE customer_id = ? AND status = 'Completed'",
            (customer_id,)
        ).fetchone()[0]

        legacy_mems_cents = db.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM memberships WHERE customer_id = ? AND sale_id IS NULL AND cancelled_at IS NULL",
            (customer_id,)
        ).fetchone()[0]
        lifetime_cents = sales_cents + legacy_mems_cents

        total_visits = db.execute(
            "SELECT COUNT(*) FROM visits WHERE customer_id = ?",
            (customer_id,)
        ).fetchone()[0]

        last_visit_row = db.execute(
            "SELECT check_in_at FROM visits WHERE customer_id = ? ORDER BY check_in_at DESC LIMIT 1",
            (customer_id,)
        ).fetchone()
        last_visit = last_visit_row[0] if last_visit_row else None

        return {
            "id": cust["id"],
            "name": f"{cust['first_name']} {cust['last_name']}".strip(),
            "first_name": cust["first_name"],
            "last_name": cust["last_name"],
            "phone": cust["phone"],
            "yearly_status": mem_sum["yearly_status"],
            "yearly_label": mem_sum["yearly_label"],
            "yearly_end_date": mem_sum["yearly_end_date"],
            "monthly_status": mem_sum["monthly_status"],
            "monthly_label": mem_sum["monthly_label"],
            "monthly_end_date": mem_sum["monthly_end_date"],
            "daily_access": daily_access,
            "has_gym_access": mem_sum["has_gym_access"],
            "discount_eligibility": discount_eligibility,
            "total_purchases": total_purchases,
            "lifetime_spending_cents": lifetime_cents,
            "lifetime_spending": money(lifetime_cents),
            "total_visits": total_visits,
            "last_visit": last_visit,
        }


@app.get("/customers/{customer_id}/memberships")
def get_customer_memberships(customer_id: int):
    today = ph_today().isoformat()
    with connect() as db:
        require_record(db, "customers", customer_id)
        mems = rows(db.execute("""
            SELECT m.*, s.receipt_no, s.payment_method
            FROM memberships m
            LEFT JOIN sales s ON s.id = m.sale_id
            WHERE m.customer_id = ?
            ORDER BY m.start_date DESC, m.id DESC
        """, (customer_id,)))
        for m in mems:
            if m["cancelled_at"]:
                m["status"] = "Cancelled"
            elif m["start_date"] <= today <= m["end_date"]:
                m["status"] = "Active"
            elif m["end_date"] < today:
                m["status"] = "Expired"
            else:
                m["status"] = "Not Yet Active"
            m["amount"] = money(m.get("amount_cents") or 0)
        return mems


@app.get("/customers/{customer_id}/sales")
def get_customer_sales(customer_id: int):
    with connect() as db:
        require_record(db, "customers", customer_id)
        sales_rows = rows(db.execute("""
            SELECT * FROM sales
            WHERE customer_id = ?
            ORDER BY id DESC
        """, (customer_id,)))
        for s in sales_rows:
            sale_id = s["id"]
            items = rows(db.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)))
            s["total"] = money(s.pop("total_cents"))
            s["amount_tendered"] = money(s.pop("amount_tendered_cents"))
            s["change"] = money(s.pop("change_cents"))
            s["subtotal"] = money(s.pop("subtotal_cents") if s.get("subtotal_cents") is not None else 0)
            s["discount"] = money(s.pop("discount_cents") if s.get("discount_cents") is not None else 0)
            for it in items:
                it["unit_price"] = money(it.pop("unit_price_cents"))
                it["line_amount"] = money(it.pop("line_amount_cents"))
                it["discount"] = money(it.pop("discount_cents") if it.get("discount_cents") is not None else 0)
            s["items"] = items
        return sales_rows


@app.get("/customers/{customer_id}/visits")
def get_customer_visits(customer_id: int):
    with connect() as db:
        require_record(db, "customers", customer_id)
        visits = rows(db.execute("""
            SELECT v.*, s.receipt_no
            FROM visits v
            LEFT JOIN sales s ON s.id = v.sale_id
            WHERE v.customer_id = ?
            ORDER BY v.check_in_at DESC
        """, (customer_id,)))
        return visits


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
        if data.request_id:
            existing_sale = db.execute("SELECT id FROM sales WHERE request_id = ?", (data.request_id,)).fetchone()
            if existing_sale:
                mem = db.execute("SELECT * FROM memberships WHERE sale_id = ?", (existing_sale[0],)).fetchone()
                if mem:
                    sale_res = get_sale_formatted(db, existing_sale[0])
                    return {"id": mem["id"], "sale_id": existing_sale[0], "sale": sale_res, **dict(mem)}

        cust = require_record(db, "customers", data.customer_id)
        customer_name = f"{cust['first_name']} {cust['last_name']}".strip()
        today_str = ph_today().isoformat()

        if data.plan in ("Monthly session", "Member session, monthly"):
            existing_m = db.execute(
                """SELECT 1 FROM memberships
                   WHERE customer_id = ? AND plan IN ('Monthly session', 'Member session, monthly') AND cancelled_at IS NULL LIMIT 1""",
                (data.customer_id,)
            ).fetchone()
            if existing_m:
                raise HTTPException(409, "Customer already has a monthly session record. Use renew instead.")
            prod = db.execute("SELECT id, price_cents FROM products WHERE name IN ('Monthly session', 'Member session, monthly')").fetchone()
            price_cents = prod["price_cents"] if prod else 120000
            prod_id = prod["id"] if prod else None
            prod_cat = "Gym Access"
        else:
            # Yearly membership
            existing = db.execute(
                "SELECT 1 FROM memberships WHERE customer_id = ? AND plan = 'Yearly membership' AND cancelled_at IS NULL LIMIT 1",
                (data.customer_id,)
            ).fetchone()
            if existing:
                raise HTTPException(409, "Customer already has a yearly membership. Use renew instead.")
            prod = db.execute("SELECT id, price_cents FROM products WHERE name = 'Yearly membership'").fetchone()
            price_cents = prod["price_cents"] if prod else 30000
            prod_id = prod["id"] if prod else None
            prod_cat = "Membership"

        total_cents = price_cents
        subtotal_cents = price_cents
        discount_cents = 0

        method = "Cash"
        if data.method:
            method = "Cash" if data.method.lower().startswith("c") else "E-Wallet"

        if data.amount_tendered is not None:
            tendered_cents = cents(data.amount_tendered)
        else:
            tendered_cents = total_cents

        if method == "Cash":
            if tendered_cents < total_cents:
                raise HTTPException(422, "Amount is less than the total due")
            change_cents = tendered_cents - total_cents
        else:
            tendered_cents = total_cents
            change_cents = 0

        created_at_str = ph_now().strftime("%Y-%m-%d %H:%M:%S")
        receipt_no = next_receipt_no(db)

        s_cur = db.execute("""
            INSERT INTO sales (
                receipt_no, customer_id, customer_name, customer_type, total_cents,
                payment_method, amount_tendered_cents, change_cents, status,
                subtotal_cents, discount_cents, membership_status, request_id, kind, created_at
            ) VALUES (?, ?, ?, 'Member', ?, ?, ?, ?, 'Completed', ?, ?, 'Active', ?, 'membership', ?)
        """, (
            receipt_no, data.customer_id, customer_name,
            total_cents, method, tendered_cents, change_cents,
            subtotal_cents, discount_cents, data.request_id, created_at_str
        ))
        sale_id = s_cur.lastrowid

        if prod_id:
            db.execute("""
                INSERT INTO sale_items (
                    sale_id, product_id, item_name, category, unit_price_cents,
                    quantity, line_amount_cents, discount_cents
                ) VALUES (?, ?, ?, ?, ?, 1, ?, 0)
            """, (sale_id, prod_id, data.plan, prod_cat, price_cents, price_cents))

        cursor = db.execute(
            """INSERT INTO memberships
               (customer_id, plan, start_date, end_date, sale_id, amount_cents, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data.customer_id, data.plan,
             data.start_date.isoformat(), data.end_date.isoformat(),
             sale_id, total_cents, created_at_str)
        )
        membership_id = cursor.lastrowid

        p_cur = db.execute(
            """INSERT INTO payments
               (customer_id, description, amount_cents, method, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (data.customer_id, f"Plan: {data.plan}", price_cents, method, created_at_str)
        )
        payment_id = p_cur.lastrowid

        sale_res = get_sale_formatted(db, sale_id)
        return {
            "id": membership_id,
            "sale_id": sale_id,
            "payment_id": payment_id,
            "sale": sale_res,
            **data.model_dump(mode="json")
        }


@app.post("/memberships/renew", status_code=201)
def renew_membership_record(data: Membership):
    if data.end_date < data.start_date:
        raise HTTPException(422, "End date must not precede start date")

    with connect() as db:
        if data.request_id:
            existing_sale = db.execute("SELECT id FROM sales WHERE request_id = ?", (data.request_id,)).fetchone()
            if existing_sale:
                mem = db.execute("SELECT * FROM memberships WHERE sale_id = ?", (existing_sale[0],)).fetchone()
                if mem:
                    sale_res = get_sale_formatted(db, existing_sale[0])
                    return {"id": mem["id"], "sale_id": existing_sale[0], "sale": sale_res, **dict(mem)}

        cust = require_record(db, "customers", data.customer_id)
        customer_name = f"{cust['first_name']} {cust['last_name']}".strip()
        today_str = ph_today().isoformat()

        mems = rows(db.execute(
            """SELECT id, plan, start_date, end_date
               FROM memberships
               WHERE customer_id = ? AND cancelled_at IS NULL
               ORDER BY start_date ASC, id ASC""",
            (data.customer_id,)
        ))

        if data.plan in ("Monthly session", "Member session, monthly"):
            plan_mems = [m for m in mems if m["plan"] in ("Monthly session", "Member session, monthly")]
            prod = db.execute("SELECT id, price_cents FROM products WHERE name IN ('Monthly session', 'Member session, monthly')").fetchone()
            price_cents = prod["price_cents"] if prod else 120000
            prod_id = prod["id"] if prod else None
            prod_cat = "Gym Access"
        else:
            plan_mems = [m for m in mems if m["plan"] == data.plan]
            prod = db.execute("SELECT id, price_cents FROM products WHERE name = 'Yearly membership'").fetchone()
            price_cents = prod["price_cents"] if prod else 30000
            prod_id = prod["id"] if prod else None
            prod_cat = "Membership"

        if not plan_mems:
            raise HTTPException(409, f"Customer has never had a {data.plan}. Use register instead.")

        has_waiting = any(m["start_date"] > today_str for m in plan_mems)
        if has_waiting:
            raise HTTPException(409, f"Customer already has a waiting renewal for {data.plan}.")

        total_cents = price_cents
        subtotal_cents = price_cents
        discount_cents = 0

        method = "Cash"
        if data.method:
            method = "Cash" if data.method.lower().startswith("c") else "E-Wallet"

        if data.amount_tendered is not None:
            tendered_cents = cents(data.amount_tendered)
        else:
            tendered_cents = total_cents

        if method == "Cash":
            if tendered_cents < total_cents:
                raise HTTPException(422, "Amount is less than the total due")
            change_cents = tendered_cents - total_cents
        else:
            tendered_cents = total_cents
            change_cents = 0

        created_at_str = ph_now().strftime("%Y-%m-%d %H:%M:%S")
        receipt_no = next_receipt_no(db)

        s_cur = db.execute("""
            INSERT INTO sales (
                receipt_no, customer_id, customer_name, customer_type, total_cents,
                payment_method, amount_tendered_cents, change_cents, status,
                subtotal_cents, discount_cents, membership_status, request_id, kind, created_at
            ) VALUES (?, ?, ?, 'Member', ?, ?, ?, ?, 'Completed', ?, ?, 'Active', ?, 'membership', ?)
        """, (
            receipt_no, data.customer_id, customer_name,
            total_cents, method, tendered_cents, change_cents,
            subtotal_cents, discount_cents, data.request_id, created_at_str
        ))
        sale_id = s_cur.lastrowid

        if prod_id:
            db.execute("""
                INSERT INTO sale_items (
                    sale_id, product_id, item_name, category, unit_price_cents,
                    quantity, line_amount_cents, discount_cents
                ) VALUES (?, ?, ?, ?, ?, 1, ?, 0)
            """, (sale_id, prod_id, data.plan, prod_cat, price_cents, price_cents))

        cursor = db.execute(
            """INSERT INTO memberships
               (customer_id, plan, start_date, end_date, sale_id, amount_cents, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data.customer_id, data.plan,
             data.start_date.isoformat(), data.end_date.isoformat(),
             sale_id, total_cents, created_at_str)
        )
        membership_id = cursor.lastrowid

        p_cur = db.execute(
            """INSERT INTO payments
               (customer_id, description, amount_cents, method, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (data.customer_id, f"Plan Renewal: {data.plan}", price_cents, method, created_at_str)
        )
        payment_id = p_cur.lastrowid

        sale_res = get_sale_formatted(db, sale_id)
        return {
            "id": membership_id,
            "sale_id": sale_id,
            "payment_id": payment_id,
            "sale": sale_res,
            **data.model_dump(mode="json")
        }


@app.get("/memberships")
def list_memberships(status: str = "all", plan: str = ""):
    status = status.strip().lower()
    if status not in ("all", "active", "expired", "upcoming"):
        raise HTTPException(422, "Invalid membership status")

    today = ph_today().isoformat()

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


def next_receipt_no(db):
    last_id = db.execute("SELECT COALESCE(MAX(id), 0) FROM sales").fetchone()[0]
    return f"R-{last_id + 1:06d}"


def get_sale_formatted(db, sale_id: int):
    sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if not sale:
        raise HTTPException(404, f"There is no sale record with ID {sale_id} right now.")
    sale = dict(sale)
    items = rows(db.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)))
    sale["total"] = money(sale.pop("total_cents"))
    sale["amount_tendered"] = money(sale.pop("amount_tendered_cents"))
    sale["change"] = money(sale.pop("change_cents"))
    sale["subtotal"] = money(sale.pop("subtotal_cents") if sale.get("subtotal_cents") is not None else 0)
    sale["discount"] = money(sale.pop("discount_cents") if sale.get("discount_cents") is not None else 0)
    for it in items:
        it["unit_price"] = money(it.pop("unit_price_cents"))
        it["line_amount"] = money(it.pop("line_amount_cents"))
        it["discount"] = money(it.pop("discount_cents") if it.get("discount_cents") is not None else 0)
    sale["items"] = items
    ts_row = db.execute("SELECT trainer_name, session_date_time FROM trainer_sessions WHERE sale_id=?", (sale_id,)).fetchone()
    if ts_row:
        sale["trainer_name"] = ts_row["trainer_name"]
        sale["session_date_time"] = ts_row["session_date_time"]
    return sale


# SALES

@app.post("/quotes")
def quote_sale(data: QuoteRequest):
    with connect() as db:
        calc = calculate_discounts(db, data.customer_id, data.items)
        return {
            "customer_id": data.customer_id,
            "customer_name": calc["customer_name"],
            "membership_status": calc["membership_status"],
            "has_gym_access": calc["mem_sum"]["has_gym_access"],
            "qualifying_types": calc["mem_sum"]["qualifying_types"],
            "items": calc["items"],
            "subtotal": money(calc["subtotal_cents"]),
            "subtotal_cents": calc["subtotal_cents"],
            "discount": money(calc["discount_cents"]),
            "discount_cents": calc["discount_cents"],
            "total": money(calc["total_cents"]),
            "total_cents": calc["total_cents"],
        }


@app.post("/daily-sessions", status_code=201)
def create_daily_session(data: DailySessionCreate):
    with connect() as db:
        if data.request_id:
            existing = db.execute("SELECT id FROM sales WHERE request_id = ?", (data.request_id,)).fetchone()
            if existing:
                res = get_sale_formatted(db, existing[0])
                res["checked_in"] = True
                return res

        prod = db.execute(
            "SELECT id, name, category, price_cents, is_active FROM products WHERE name = ? AND is_active = 1",
            (DAILY_PRODUCT_NAME,)
        ).fetchone()
        if not prod:
            prod = db.execute(
                "SELECT id, name, category, price_cents, is_active FROM products WHERE category = 'Gym Access' AND is_active = 1 ORDER BY id DESC"
            ).fetchone()
        if not prod:
            raise HTTPException(500, "Daily session product not found in catalog")

        calc = calculate_discounts(db, data.customer_id, [{"product_id": prod["id"], "quantity": 1}])
        total_cents = calc["total_cents"]
        subtotal_cents = calc["subtotal_cents"]
        discount_cents = calc["discount_cents"]

        tendered_cents = cents(data.amount_tendered)
        if data.payment_method == "Cash":
            if tendered_cents < total_cents:
                raise HTTPException(422, "Amount is less than the total due")
            change_cents = tendered_cents - total_cents
        else:
            tendered_cents = total_cents
            change_cents = 0

        receipt_no = next_receipt_no(db)
        customer_type = "Member" if calc["membership_status"] == "Active" else "Non-member"
        created_at_str = ph_now().strftime("%Y-%m-%d %H:%M:%S")

        cur = db.execute("""
            INSERT INTO sales (
                receipt_no, customer_id, customer_name, customer_type, total_cents,
                payment_method, amount_tendered_cents, change_cents, status,
                subtotal_cents, discount_cents, membership_status, request_id, kind, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Completed', ?, ?, ?, ?, 'daily_session', ?)
        """, (
            receipt_no, data.customer_id, calc["customer_name"], customer_type,
            total_cents, data.payment_method, tendered_cents, change_cents,
            subtotal_cents, discount_cents, calc["membership_status"], data.request_id, created_at_str
        ))
        sale_id = cur.lastrowid

        for it in calc["items"]:
            db.execute("""
                INSERT INTO sale_items (
                    sale_id, product_id, item_name, category, unit_price_cents,
                    quantity, line_amount_cents, discount_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sale_id, it["product_id"], it["item_name"], it["category"],
                it["unit_price_cents"], it["quantity"], it["total_cents"], it["discount_cents"]
            ))

        db.execute("""
            INSERT INTO visits (customer_id, check_in_at, used, sale_id)
            VALUES (?, ?, 1, ?)
        """, (data.customer_id, created_at_str, sale_id))

        res = get_sale_formatted(db, sale_id)
        res["checked_in"] = True
        return res


@app.post("/sales", status_code=201)
def create_sale(data: SaleCreate):
    with connect() as db:
        if data.request_id:
            existing = db.execute("SELECT id FROM sales WHERE request_id = ?", (data.request_id,)).fetchone()
            if existing:
                return get_sale_formatted(db, existing[0])

        if not data.items:
            raise HTTPException(422, "Add at least one item first")

        calc = calculate_discounts(db, data.customer_id, data.items)
        total_cents = calc["total_cents"]
        subtotal_cents = calc["subtotal_cents"]
        discount_cents = calc["discount_cents"]

        tendered_cents = cents(data.amount_tendered)
        if data.payment_method == "Cash":
            if tendered_cents < total_cents:
                raise HTTPException(422, "Amount is less than the total due")
            change_cents = tendered_cents - total_cents
        else:
            tendered_cents = total_cents
            change_cents = 0

        receipt_no = next_receipt_no(db)
        customer_type = "Member" if calc["membership_status"] == "Active" else "Non-member"
        created_at_str = ph_now().strftime("%Y-%m-%d %H:%M:%S")

        cur = db.execute("""
            INSERT INTO sales (
                receipt_no, customer_id, customer_name, customer_type, total_cents,
                payment_method, amount_tendered_cents, change_cents, status,
                subtotal_cents, discount_cents, membership_status, request_id, kind, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Completed', ?, ?, ?, ?, 'product', ?)
        """, (
            receipt_no, data.customer_id, calc["customer_name"], customer_type,
            total_cents, data.payment_method, tendered_cents, change_cents,
            subtotal_cents, discount_cents, calc["membership_status"], data.request_id, created_at_str
        ))
        sale_id = cur.lastrowid

        for it in calc["items"]:
            db.execute("""
                INSERT INTO sale_items (
                    sale_id, product_id, item_name, category, unit_price_cents,
                    quantity, line_amount_cents, discount_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sale_id, it["product_id"], it["item_name"], it["category"],
                it["unit_price_cents"], it["quantity"], it["total_cents"], it["discount_cents"]
            ))

        return get_sale_formatted(db, sale_id)


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
            sale["subtotal"] = money(sale.pop("subtotal_cents") if sale.get("subtotal_cents") is not None else 0)
            sale["discount"] = money(sale.pop("discount_cents") if sale.get("discount_cents") is not None else 0)
            for it in items:
                it["unit_price"] = money(it.pop("unit_price_cents"))
                it["line_amount"] = money(it.pop("line_amount_cents"))
                it["discount"] = money(it.pop("discount_cents") if it.get("discount_cents") is not None else 0)
            sale["items"] = items
        return records


@app.get("/sales/{sale_id}")
def get_sale(sale_id: int):
    with connect() as db:
        return get_sale_formatted(db, sale_id)


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
        current_month = ph_today().strftime("%Y-%m")
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
    today_str = ph_today().isoformat()
    now_dt = ph_now()

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
        if data.request_id:
            existing = db.execute("SELECT id FROM sales WHERE request_id = ?", (data.request_id,)).fetchone()
            if existing:
                return get_sale_formatted(db, existing[0])

        trainer = db.execute("SELECT * FROM trainers WHERE id=? AND status='Active'", (data.trainer_id,)).fetchone()
        if not trainer:
            raise HTTPException(422, "Invalid choice")

        if data.customer_id is not None:
            cust = db.execute("SELECT * FROM customers WHERE id=?", (data.customer_id,)).fetchone()
            if not cust:
                raise HTTPException(404, f"Customer with ID {data.customer_id} was not found.")
            # Use the same active/cancelled membership validation as purchase quotes.
            member_status = membership_summary(db, data.customer_id)
            customer_type = "Member" if member_status["yearly_status"] == "Active" else "Non-member"
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

        created_at_str = ph_now().strftime("%Y-%m-%d %H:%M:%S")
        cur = db.execute("""
            INSERT INTO sales (receipt_no, customer_id, customer_name, customer_type, total_cents,
                               payment_method, amount_tendered_cents, change_cents, status,
                               subtotal_cents, discount_cents, membership_status, request_id, kind, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Completed', ?, 0, ?, ?, 'trainer', ?)
        """, (receipt_no, data.customer_id, customer_name, customer_type, price_cents,
              data.payment_method, tendered_cents, change_cents, price_cents, customer_type, data.request_id, created_at_str))
        sale_id = cur.lastrowid

        db.execute("""
            INSERT INTO sale_items (sale_id, product_id, item_name, category, unit_price_cents, quantity, line_amount_cents, discount_cents)
            VALUES (?, ?, ?, 'Coaching', ?, 1, ?, 0)
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
            "created_at": ph_now().strftime("%Y-%m-%d %H:%M"),
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
