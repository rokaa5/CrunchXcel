"""Regression tests for unified customer, product, service and payment search.

Run with: python -m unittest discover -s tests -v
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
    Customer,
    DailySessionCreate,
    MembershipRegistration,
    SaleCreate,
    SaleLineItemCreate,
    TrainerSessionCreate,
    ph_now,
    ph_today,
)


class TransactionSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db_override = patch.object(database, "DB_PATH", Path(self.temp.name) / "gym.db")
        db_override.start()
        self.addCleanup(db_override.stop)
        database.initialize_database()

    def customer(self, first="Alex", last="Member", phone="09181234567"):
        with database.connect() as db:
            result = db.execute(
                "INSERT INTO customers (first_name, last_name, phone) VALUES (?, ?, ?)",
                (first, last, phone),
            )
            return result.lastrowid

    def product(self, name="Bottled water"):
        with database.connect() as db:
            p = db.execute(
                "SELECT id, price_cents FROM products WHERE name = ?",
                (name,),
            ).fetchone()
            self.assertIsNotNone(p)
            return p["id"], p["price_cents"]

    def sale(self, customer_id=None, name="Bottled water", quantity=1):
        product_id, price = self.product(name)
        return api.create_sale(SaleCreate(
            customer_id=customer_id,
            payment_method="Cash",
            amount_tendered=Decimal(price * quantity) / 100,
            items=[SaleLineItemCreate(product_id=product_id, quantity=quantity)],
        ))

    def test_customer_name_and_id_find_all_purchases_without_duplicate_membership(self):
        cid = self.customer()
        membership = api.create_membership(MembershipRegistration(
            customer_id=cid,
            plan="Yearly membership",
            start_date=ph_today(),
            end_date=ph_today() + timedelta(days=365),
            method="Cash",
            amount_tendered=Decimal("300.00"),
        ))
        purchase = self.sale(customer_id=cid)
        self.sale()  # Anonymous: must not be returned under the registered customer.
        by_name = api.search_transactions("customer", "Alex Member")
        by_id = api.search_transactions("customer", str(cid))
        expected = {membership["sale"]["receipt_no"], purchase["receipt_no"]}
        self.assertEqual({r["reference"] for r in by_name}, expected)
        self.assertEqual({r["reference"] for r in by_id}, expected)
        self.assertTrue(all(r["record_type"] == "sale" for r in by_name))
        self.assertTrue(all(r["customer_id"] == cid for r in by_name))

    def test_product_name_and_id_return_every_matching_receipt(self):
        first = self.sale(quantity=2)
        second = self.sale()
        other = self.sale(name="Cobra")
        product_id, _ = self.product()
        expected = {first["receipt_no"], second["receipt_no"]}
        self.assertEqual(
            {r["reference"] for r in api.search_transactions("item", "Bottled water")},
            expected,
        )
        self.assertEqual(
            {r["reference"] for r in api.search_transactions("item", str(product_id))},
            expected,
        )
        self.assertNotIn(other["receipt_no"], expected)
        self.assertTrue(
            any("2 x Bottled water" in r["item_names"] for r in api.search_transactions("item", "water"))
        )

    def test_service_name_category_and_id_work_for_anonymous_daily_session(self):
        daily = api.create_daily_session(DailySessionCreate(
            customer_id=None,
            payment_method="Cash",
            amount_tendered=Decimal("70.00"),
        ))
        product_id, _ = self.product("Daily session")
        for term in ("Daily session", "Gym Access", str(product_id)):
            matches = api.search_transactions("item", term)
            self.assertIn(daily["receipt_no"], {r["reference"] for r in matches})

    def test_trainer_booking_searchable_as_a_service_and_by_customer(self):
        with database.connect() as db:
            product = db.execute(
                "SELECT id, price_cents FROM products "
                "WHERE category = 'Coaching' AND applies_to = 'Non-members only' LIMIT 1"
            ).fetchone()
            trainer_id = db.execute(
                "SELECT id FROM trainers WHERE status = 'Active' LIMIT 1"
            ).fetchone()["id"]
        booking = api.create_trainer_session(TrainerSessionCreate(
            new_customer=Customer(
                first_name="Maria", last_name="Santos", phone="09192345678"
            ),
            product_id=product["id"],
            trainer_id=trainer_id,
            session_label="Personal Trainer Session",
            session_datetime=(ph_now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M"),
            payment_method="Cash",
            amount_tendered=Decimal(product["price_cents"]) / 100,
        ))
        for scope, query in (
            ("item", "Coaching"),
            ("item", "Trainer"),
            ("item", str(product["id"])),
            ("customer", "Maria Santos"),
            ("customer", str(booking["customer_id"])),
        ):
            rows = api.search_transactions(scope, query)
            self.assertIn(booking["receipt_no"], {r["reference"] for r in rows})

    def test_same_name_customers_are_distinguished_by_id(self):
        first = self.customer(first="Jamie", last="Cruz", phone="09181234567")
        second = self.customer(first="Jamie", last="Cruz", phone="09192345678")
        self.sale(customer_id=first)
        self.sale(customer_id=second)
        results = api.search_transactions("customer", "Jamie Cruz")
        self.assertEqual({r["customer_id"] for r in results}, {first, second})
        filtered = api.search_transactions("customer", str(first))
        self.assertEqual({r["customer_id"] for r in filtered}, {first})

    def test_payment_id_receipt_and_legacy_purchase_records(self):
        customer_id = self.customer()
        item_id, price = self.product()
        with database.connect() as db:
            payment = db.execute(
                "INSERT INTO payments (customer_id, description, amount_cents, method) "
                "VALUES (?, 'Bottled water x1', ?, 'Cash')",
                (customer_id, price),
            )
            payment_id = payment.lastrowid
            db.execute(
                "INSERT INTO purchases "
                "(customer_id, product_id, quantity, unit_price_cents, payment_id) "
                "VALUES (?, ?, 1, ?, ?)",
                (customer_id, item_id, price, payment_id),
            )
        legacy_ref = f"PAY-{payment_id:06d}"
        results = api.search_transactions("item", str(item_id))
        self.assertIn(legacy_ref, {r["reference"] for r in results})
        self.assertEqual(
            api.search_transactions("payment", str(payment_id))[0]["reference"], legacy_ref
        )
        self.assertEqual(
            api.search_transactions("payment", legacy_ref)[0]["reference"], legacy_ref
        )
        receipt = self.sale()
        self.assertEqual(
            api.search_transactions("payment", receipt["receipt_no"])[0]["reference"],
            receipt["receipt_no"],
        )

    def test_search_is_literal_for_sql_wildcards(self):
        self.sale()
        self.assertEqual(api.search_transactions("item", "%"), [])
        self.assertEqual(api.search_transactions("customer", "_"), [])

    def test_search_requires_valid_scope_and_term(self):
        for scope, query in (("wrong", "test"), ("item", " ")):
            with self.assertRaises(HTTPException) as error:
                api.search_transactions(scope, query)
            self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
