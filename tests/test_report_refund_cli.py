"""Tests for simplified report screens and manual refund CLI interaction."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main


class ReportScreenTests(unittest.TestCase):
    def test_daily_transactions_one_page_uses_enter_and_lists_dates(self):
        sample = [{
            "period": "2026-11-07",
            "transactions": [{
                "receipt_no": "R-000010", "time": "02:55",
                "item_name": "2 x Bottled water",
                "total": "20.00", "status": "Completed",
            }],
        }]
        buf = io.StringIO()
        with (
            patch.object(main, "request", return_value=sample),
            patch.object(main, "pause") as pause,
            patch.object(main, "header", side_effect=lambda *a, **k: print("DAILY TRANSACTIONS")),
            redirect_stdout(buf),
        ):
            main.daily_transactions()
        self.assertIn("R-000010", buf.getvalue())
        self.assertIn("2026-11-07", buf.getvalue())
        pause.assert_called_once()

    def test_daily_transactions_more_than_ten_show_page_controls(self):
        sample = [{
            "period": "2026-11-07",
            "transactions": [
                {
                    "receipt_no": f"R-{n:06d}", "time": "02:55",
                    "item_name": "Bottled water", "total": "10.00",
                    "status": "Completed",
                }
                for n in range(11)
            ],
        }]
        buf = io.StringIO()
        with (
            patch.object(main, "request", return_value=sample),
            patch.object(main, "header", side_effect=lambda *a, **k: print("DAILY TRANSACTIONS")),
            patch("builtins.input", side_effect=[">", "0"]),
            redirect_stdout(buf),
        ):
            main.daily_transactions()
        self.assertIn("Page 1 of 2", buf.getvalue())
        self.assertIn("Page 2 of 2", buf.getvalue())

    def test_monthly_one_period_uses_enter_without_choice(self):
        sample = [{
            "period": "2026-11",
            "categories": [{"category": "Beverage", "transactions": 1, "amount": "10.00"}],
            "total_transactions": 1, "total_sales": "10.00",
            "gross_sales": "10.00", "refunds_total": "0.00",
        }]
        buf = io.StringIO()
        with (
            patch.object(main, "request", return_value=sample),
            patch.object(main, "pause") as pause,
            patch.object(main, "header", side_effect=lambda *a, **k: print("MONTHLY SALES REPORT")),
            patch("builtins.input", side_effect=AssertionError("Monthly report should not ask for a choice")),
            redirect_stdout(buf),
        ):
            main.monthly_sales_report()
        self.assertIn("Net Sales", buf.getvalue())
        self.assertIn("Gross Sales", buf.getvalue())
        pause.assert_called_once()

    def test_monthly_multiple_periods_can_navigate(self):
        sample = [
            {"period": "2026-11", "categories": [], "total_transactions": 0,
             "total_sales": "0.00", "gross_sales": "0.00", "refunds_total": "0.00"},
            {"period": "2026-10", "categories": [], "total_transactions": 0,
             "total_sales": "0.00", "gross_sales": "0.00", "refunds_total": "0.00"},
        ]
        buf = io.StringIO()
        with (
            patch.object(main, "request", return_value=sample),
            patch.object(main, "header", side_effect=lambda *a, **k: print("MONTHLY SALES REPORT")),
            patch("builtins.input", side_effect=[">", "0"]),
            redirect_stdout(buf),
        ):
            main.monthly_sales_report()
        self.assertIn("Month: 2026-11", buf.getvalue())
        self.assertIn("Month: 2026-10", buf.getvalue())

    def test_refund_purchase_is_submitted_once_after_confirmation(self):
        transaction = [{
            "record_type": "sale", "record_id": 5, "reference": "R-000005",
            "item_names": "Daily session", "amount": "70.00",
            "status": "Completed",
        }]
        sale = {
            "id": 5, "receipt_no": "R-000005", "customer_name": "Walk-in",
            "payment_method": "Cash", "total": "70.00",
            "kind": "daily_session",
            "items": [{"quantity": 1, "item_name": "Daily session"}],
        }
        refund = {
            "refund_no": "REF-000001", "receipt_no": "R-000005",
            "amount": "70.00", "method": "Cash",
            "reason": "Wrong purchase", "created_at": "2026-11-07 03:00:00",
        }
        calls = []
        def fake_request(method, path, data=None, params=None):
            calls.append((method, path, data))
            if path == "/transactions/search":
                return transaction if len([a for a in calls if a[1] == path]) == 1 else []
            if path == "/sales/5":
                return sale
            if path == "/sales/5/refund":
                return refund
            return None

        with (
            patch.object(main, "request", side_effect=fake_request),
            patch.object(main, "header", side_effect=lambda *a, **k: None),
            patch.object(main, "ask", return_value="Wrong purchase"),
            patch.object(main, "ask_payment_method", return_value="Cash"),
            patch.object(main, "confirm", return_value=True),
            patch.object(main, "pause"),
            patch("builtins.input", side_effect=["R-000005", "0"]),
            redirect_stdout(io.StringIO()),
        ):
            main.refund_purchase_session()
        refund_posts = [c for c in calls if c[1] == "/sales/5/refund"]
        self.assertEqual(len(refund_posts), 1)
        self.assertEqual(refund_posts[0][2]["refund_method"], "Cash")


if __name__ == "__main__":
    unittest.main()
