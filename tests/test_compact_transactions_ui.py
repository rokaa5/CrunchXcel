"""CLI regression tests for the compact transaction list.

Run: python -m unittest discover -s tests -v
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main


def transaction(idx, category, name, customer_id=None):
    return {
        "reference": f"R-{idx:06d}",
        "record_type": "sale",
        "record_id": idx,
        "created_at": "2026-11-07 02:55:00",
        "customer_id": customer_id,
        "customer_name": "Sample Member" if customer_id else "Walk-in",
        "item_names": name,
        "amount": "20.00",
        "payment_method": "Cash",
        "status": "Completed",
        "categories": [category],
    }


class CompactTransactionDisplayTests(unittest.TestCase):
    def run_screen(self, records, commands, extra_patches=None):
        stream = io.StringIO()
        with (
            patch.object(main, "request", return_value=records) as request_fn,
            patch.object(
                main, "header",
                side_effect=lambda title, **kwargs: print(f"SCREEN: {title}")
            ),
            patch("builtins.input", side_effect=commands),
            redirect_stdout(stream),
        ):
            main.search_transactions_ui()
        return stream.getvalue(), request_fn

    def test_category_filter_shows_only_matching_entries(self):
        rows = [
            transaction(1, "products", "Bottled water"),
            transaction(2, "monthly", "Monthly session", customer_id=4),
            transaction(3, "daily", "Daily session"),
        ]
        display, _ = self.run_screen(rows, ["2", "0"])
        filtered_page = display.rsplit("SCREEN: SEARCH TRANSACTIONS", 1)[-1]
        self.assertIn("Category: Monthly Session", filtered_page)
        self.assertIn("Monthly session", filtered_page)
        self.assertNotIn("Bottled water", filtered_page)
        self.assertNotIn("Daily session", filtered_page)

    def test_five_entries_per_page_and_next_navigation(self):
        rows = [
            transaction(idx, "products", f"Product number {idx}")
            for idx in range(1, 7)
        ]
        display, _ = self.run_screen(rows, ["n", "0"])
        first, last = display.split("SCREEN: SEARCH TRANSACTIONS")[1:]
        self.assertIn("Page 1 of 2", first)
        self.assertIn("R-000005", first)
        self.assertNotIn("R-000006", first)
        self.assertIn("Page 2 of 2", last)
        self.assertIn("R-000006", last)
        self.assertNotIn("R-000001", last)

    def test_receipt_opens_existing_sale_details(self):
        row = transaction(42, "trainer", "Personal Trainer Session", customer_id=3)
        with (
            patch.object(main, "request", return_value=[row]),
            patch.object(main, "header", side_effect=lambda *args, **kwargs: None),
            patch.object(main, "view_sale_details") as details,
            patch("builtins.input", side_effect=["R-000042", "0"]),
            redirect_stdout(io.StringIO()),
        ):
            main.search_transactions_ui()
        details.assert_called_once_with(42)

    def test_search_is_passed_to_api_and_keeps_category_selected(self):
        rows = [transaction(1, "products", "Bottled water")]
        calls = []
        def fake_request(method, path, params=None):
            calls.append(params)
            return rows

        with (
            patch.object(main, "request", side_effect=fake_request),
            patch.object(main, "header", side_effect=lambda *args, **kwargs: None),
            patch("builtins.input", side_effect=["5", "water", "0"]),
            redirect_stdout(io.StringIO()),
        ):
            main.search_transactions_ui()
        self.assertEqual(calls, [None, None, {"query": "water"}])


if __name__ == "__main__":
    unittest.main()
