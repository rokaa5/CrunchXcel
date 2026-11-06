"""Regression tests for new-customer transactions and future trainer bookings.

Run: python -m unittest discover -s tests -v
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
from models import Customer, DailySessionCreate, MembershipRegistration, TrainerSessionCreate, ph_now, ph_today


class PurchaseRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_override = patch.object(database, "DB_PATH", Path(self.tmp.name) / "gym.db")
        self.db_override.start()
        self.addCleanup(self.db_override.stop)
        database.initialize_database()

    @staticmethod
    def new_customer(phone="09181234567"):
        return Customer(first_name="Test", last_name="Visitor", phone=phone)

    def register_plan(self, name="Yearly membership", phone="09181234567"):
        today = ph_today()
        end = api.add_one_year(today) if name == "Yearly membership" else api.add_one_month(today)
        return api.create_membership(MembershipRegistration(
            new_customer=self.new_customer(phone),
            plan=name, start_date=today, end_date=end,
            method="Cash",
            amount_tendered=Decimal("300.00" if name == "Yearly membership" else "1200.00"),
        ))

    def test_new_yearly_membership_assigns_customer_and_receipt(self):
        result = self.register_plan()
        cid = result["customer_id"]
        self.assertGreater(cid, 0)
        self.assertEqual(result["sale"]["customer_id"], cid)
        with database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memberships").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
        active = api.list_customers(eligibility="active_yearly")
        self.assertEqual([r["id"] for r in active], [cid])
        self.assertEqual(api.list_customers(eligibility="non_yearly"), [])

    def test_first_time_monthly_customer_needs_no_existing_id(self):
        result = self.register_plan("Monthly session")
        self.assertGreater(result["customer_id"], 0)
        self.assertEqual(result["sale"]["customer_id"], result["customer_id"])
        self.assertEqual(len(api.list_customers(eligibility="non_yearly")), 1)

    def test_duplicate_phone_rolls_back_new_membership(self):
        self.register_plan()
        with self.assertRaises(HTTPException) as err:
            self.register_plan("Monthly session")
        self.assertEqual(err.exception.status_code, 409)
        with database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memberships").fetchone()[0], 1)

    def test_future_nonmember_trainer_booking_registers_customer(self):
        with database.connect() as db:
            trainer_id = db.execute("SELECT id FROM trainers WHERE status='Active' LIMIT 1").fetchone()[0]
            product = db.execute(
                "SELECT id, price_cents FROM products "
                "WHERE category='Coaching' AND applies_to='Non-members only' LIMIT 1"
            ).fetchone()
        future = (ph_now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        result = api.create_trainer_session(TrainerSessionCreate(
            new_customer=self.new_customer(),
            trainer_id=trainer_id,
            product_id=product["id"],
            session_datetime=future,
            payment_method="Cash",
            amount_tendered=Decimal(product["price_cents"]) / 100,
        ))
        self.assertGreater(result["customer_id"], 0)
        self.assertEqual(result["session_date_time"], future)
        self.assertEqual(result["customer_type"], "Non-member")
        with database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM trainer_sessions").fetchone()[0], 1)

    def test_invalid_trainer_does_not_create_customer(self):
        with database.connect() as db:
            product_id = db.execute(
                "SELECT id FROM products WHERE category='Coaching' "
                "AND applies_to='Non-members only' LIMIT 1"
            ).fetchone()[0]
        with self.assertRaises(HTTPException) as err:
            api.create_trainer_session(TrainerSessionCreate(
                new_customer=self.new_customer(),
                trainer_id=999999,
                product_id=product_id,
                session_datetime=(ph_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
                payment_method="Cash",
                amount_tendered=Decimal("140.00"),
            ))
        self.assertEqual(err.exception.status_code, 422)
        with database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 0)


    def test_anonymous_daily_session_saves_receipt_without_customer_visit(self):
        data = DailySessionCreate(
            customer_id=None,
            payment_method="Cash",
            amount_tendered=Decimal("100.00"),
            request_id="anonymous-daily-test",
        )
        result = api.create_daily_session(data)
        self.assertIsNone(result["customer_id"])
        self.assertEqual(result["customer_name"], "Walk-in")
        self.assertEqual(result["total"], "70.00")
        self.assertEqual(result["change"], "30.00")
        self.assertFalse(result["checked_in"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["quantity"], 1)

        repeated = api.create_daily_session(data)
        self.assertEqual(repeated["receipt_no"], result["receipt_no"])
        self.assertFalse(repeated["checked_in"])

        with database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sale_items").fetchone()[0], 1)

    def test_registered_member_daily_session_creates_one_visit(self):
        customer_id = self.register_plan()["customer_id"]
        result = api.create_daily_session(DailySessionCreate(
            customer_id=customer_id,
            payment_method="Cash",
            amount_tendered=Decimal("50.00"),
            request_id="member-daily-test",
        ))
        self.assertEqual(result["customer_id"], customer_id)
        self.assertEqual(result["total"], "50.00")
        self.assertTrue(result["checked_in"])
        with database.connect() as db:
            visit = db.execute(
                "SELECT customer_id, sale_id FROM visits WHERE sale_id = ?",
                (result["id"],),
            ).fetchone()
            self.assertIsNotNone(visit)
            self.assertEqual(visit["customer_id"], customer_id)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
