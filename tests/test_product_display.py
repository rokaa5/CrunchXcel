"""Tests for anonymous product display and detailed item names in sales reports.

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import api
import database
import main
from models import SaleCreate, SaleLineItemCreate


class ProductDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db_patch = patch.object(database, "DB_PATH", Path(self.temp.name) / "gym.db")
        db_patch.start()
        self.addCleanup(db_patch.stop)
        database.initialize_database()

    def test_wrapped_product_rows_preserve_full_item_name(self):
        name = "Optimum Nutrition Micronized Creatine Powder, 300 g (60 servings)"
        output = io.StringIO()
        with redirect_stdout(output):
            main.print_table_row(
                {"id": 14, "name": name, "category": "Supplement", "price": "1845.00"},
                [
                    ("ID", "id", 4),
                    ("Item Name", "name", 30),
                    ("Category", "category", 12),
                    ("Price", "price", 8, "right"),
                ],
            )
        lines = [line for line in output.getvalue().splitlines() if line]
        self.assertGreater(len(lines), 1)
        wrapped = " ".join(line.split("|")[1].strip() for line in lines)
        self.assertEqual(wrapped, name)
        self.assertTrue(all(len(line.split("|")[1].strip()) <= 30 for line in lines))

    def test_daily_report_displays_multiple_products_not_buyer(self):
        with database.connect() as db:
            products = db.execute(
                "SELECT id, name, price_cents FROM products "
                "WHERE name IN ('Bottled water', 'Optimum Nutrition Micronized Creatine Powder, 300 g (60 servings)') "
                "ORDER BY id"
            ).fetchall()
        self.assertEqual(len(products), 2)
        price_cents = sum(p["price_cents"] * (2 if p["name"] == "Bottled water" else 1) for p in products)
        sale = api.create_sale(SaleCreate(
            customer_id=None,
            payment_method="Cash",
            amount_tendered=Decimal(price_cents) / 100,
            items=[
                SaleLineItemCreate(
                    product_id=p["id"],
                    quantity=2 if p["name"] == "Bottled water" else 1,
                ) for p in products
            ],
            request_id="product-display-report-test",
        ))
        report = api.sales_report("daily")
        transaction = next(
            tx
            for day in report
            for tx in day["transactions"]
            if tx["receipt_no"] == sale["receipt_no"]
        )
        self.assertIn("2 x Bottled water", transaction["item_name"])
        self.assertIn("Optimum Nutrition Micronized Creatine Powder", transaction["item_name"])
        self.assertNotIn("Walk-in", transaction["item_name"])


if __name__ == "__main__":
    unittest.main()
