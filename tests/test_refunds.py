"""Regression tests for recorded full refunds and revised financial reports.

Run: python -m unittest discover -s tests -v
All tests use a temporary SQLite database, never the user's gym.db.
"""
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import api
import database
from models import (
    Customer, DailySessionCreate, MembershipRegistration, RefundCreate,
    SaleCreate, SaleLineItemCreate, TrainerSessionCreate, ph_now, ph_today,
)


class RefundTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        override = patch.object(database, "DB_PATH", Path(self.folder.name) / "gym.db")
        override.start()
        self.addCleanup(override.stop)
        database.initialize_database()

    def customer(self):
        with database.connect() as db:
            return db.execute(
                "INSERT INTO customers(first_name,last_name,phone) VALUES(?,?,?)",
                ("Test", "Customer", "09181234567"),
            ).lastrowid

    def water_sale(self, customer_id=None):
        with database.connect() as db:
            product_id = db.execute(
                "SELECT id FROM products WHERE name='Bottled water'"
            ).fetchone()[0]
        return api.create_sale(SaleCreate(
            customer_id=customer_id,
            payment_method="Cash",
            amount_tendered=Decimal("20.00"),
            items=[SaleLineItemCreate(product_id=product_id, quantity=1)],
        ))

    def refund(self, sale_id, method="Cash"):
        return api.refund_sale(
            sale_id,
            RefundCreate(reason="Customer requested a return", refund_method=method),
        )

    def test_refund_creates_single_immutable_ledger_entry(self):
        sale = self.water_sale()
        refund = self.refund(sale["id"])
        self.assertEqual(refund["receipt_no"], sale["receipt_no"])
        self.assertEqual(refund["refund_no"], "REF-000001")
        self.assertEqual(refund["amount"], "10.00")
        self.assertEqual(refund["method"], "Cash")

        returned = api.get_sale(sale["id"])
        self.assertEqual(returned["status"], "Refunded")
        self.assertEqual(returned["refunded_amount"], "10.00")
        self.assertEqual(len(api.list_refunds()), 1)
        self.assertEqual(api.list_sales(status="Refunded")[0]["id"], sale["id"])
        self.assertEqual(api.list_sales(status="Completed"), [])

        with self.assertRaises(HTTPException) as context:
            self.refund(sale["id"])
        self.assertEqual(context.exception.status_code, 409)
        with database.connect() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM refunds").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT status FROM sales WHERE id=?", (sale["id"],)).fetchone()[0],
                "Completed",
            )

    def test_same_day_net_report_includes_negative_refund(self):
        sale = self.water_sale()
        self.refund(sale["id"])
        daily = api.sales_report("daily")[0]
        monthly = api.sales_report("monthly")[0]
        for report in (daily, monthly):
            self.assertEqual(report["gross_sales"], "10.00")
            self.assertEqual(report["refunds_total"], "10.00")
            self.assertEqual(report["total_sales"], "0.00")
            self.assertEqual(report["total_transactions"], 2)
            categories = {row["category"]: row["amount"] for row in report["categories"]}
            self.assertEqual(categories["Beverage"], "10.00")
            self.assertEqual(categories["Refunds"], "-10.00")
        daily_records = api.sales_report("daily")[0]["transactions"]
        self.assertEqual({t["receipt_no"] for t in daily_records}, {"R-000001", "REF-000001"})
        self.assertEqual(
            {t["reference"] for t in api.search_transactions()},
            {"R-000001", "REF-000001"},
        )
        self.assertEqual(
            api.search_transactions(query="REF-000001")[0]["record_type"], "refund"
        )
        self.assertEqual(
            api.get_refund(1)["refund_no"], "REF-000001"
        )

    def test_refund_is_accounted_for_on_its_own_date(self):
        sale = self.water_sale()
        later = ph_now() + timedelta(days=2)
        with patch.object(api, "ph_now", return_value=later):
            self.refund(sale["id"])
        days = {r["period"]: r for r in api.sales_report("daily")}
        original_day = ph_today().isoformat()
        refund_day = later.date().isoformat()
        self.assertEqual(days[original_day]["total_sales"], "10.00")
        self.assertEqual(days[refund_day]["total_sales"], "-10.00")
        self.assertEqual(days[refund_day]["gross_sales"], "0.00")
        self.assertEqual(days[refund_day]["refunds_count"], 1)

    def test_membership_refund_removes_membership_benefits(self):
        cid = self.customer()
        today = ph_today()
        result = api.create_membership(MembershipRegistration(
            customer_id=cid,
            plan="Yearly membership",
            start_date=today,
            end_date=api.add_one_year(today),
            method="Cash",
            amount_tendered=Decimal("300.00"),
        ))
        self.assertEqual(api.get_customer_overview(cid)["yearly_status"], "Active")
        self.refund(result["sale_id"])
        overview = api.get_customer_overview(cid)
        self.assertNotEqual(overview["yearly_status"], "Active")
        self.assertEqual(overview["lifetime_spending"], "0.00")
        report = api.membership_report()
        self.assertEqual(report["yearly"]["active"], 0)
        self.assertEqual(api.get_customer_memberships(cid)[0]["status"], "Cancelled")

    def test_monthly_membership_summary_counts_current_monthly_plan(self):
        cid = self.customer()
        today = ph_today()
        result = api.create_membership(MembershipRegistration(
            customer_id=cid,
            plan="Monthly session",
            start_date=today,
            end_date=api.add_one_month(today),
            method="Cash",
            amount_tendered=Decimal("1200.00"),
        ))
        self.assertEqual(api.membership_report()["monthly"]["active"], 1)
        self.refund(result["sale_id"])
        self.assertEqual(api.membership_report()["monthly"]["active"], 0)

    def test_trainer_refund_cancels_booking(self):
        with database.connect() as db:
            coach = db.execute(
                "SELECT id FROM trainers WHERE status='Active' LIMIT 1"
            ).fetchone()[0]
            product = db.execute(
                "SELECT id, price_cents FROM products WHERE category='Coaching' "
                "AND applies_to='Non-members only' LIMIT 1"
            ).fetchone()
        booking = api.create_trainer_session(TrainerSessionCreate(
            trainer_id=coach,
            product_id=product["id"],
            new_customer=Customer(
                first_name="New", last_name="Visitor", phone="09192345678"
            ),
            session_datetime=ph_now().strftime("%Y-%m-%d %H:%M"),
            payment_method="Cash",
            amount_tendered=Decimal(product["price_cents"]) / 100,
        ))
        cid = booking["customer_id"]
        self.assertEqual(api.customer_trainer_sessions_count(cid)["count"], 1)
        self.refund(booking["sale_id"])
        self.assertEqual(api.customer_trainer_sessions_count(cid)["count"], 0)
        with database.connect() as db:
            self.assertIsNotNone(db.execute(
                "SELECT cancelled_at FROM trainer_sessions WHERE sale_id=?",
                (booking["sale_id"],),
            ).fetchone()[0])

    def test_voided_sale_cannot_be_refunded(self):
        sale = self.water_sale()
        with database.connect() as db:
            db.execute("UPDATE sales SET status='Voided' WHERE id=?", (sale["id"],))
        with self.assertRaises(HTTPException) as err:
            self.refund(sale["id"])
        self.assertEqual(err.exception.status_code, 409)
        self.assertNotIn("/sales/{sale_id}/void", [r.path for r in api.app.routes])

    def test_payment_methods_report_is_net_of_refunds(self):
        sale = self.water_sale()
        self.refund(sale["id"], "Cash")
        rows = api.payment_methods_report()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], "0.00")
        self.assertEqual(rows[0]["refunds"], "10.00")


if __name__ == "__main__":
    unittest.main()
