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
        display, _ = self.run_screen(rows, ["2", "0", "0"])
        filtered_page = display.split("SCREEN: SEARCH TRANSACTIONS")[2]
        self.assertIn("Category: Monthly Session", filtered_page)
        self.assertIn("Monthly session", filtered_page)
        self.assertNotIn("Bottled water", filtered_page)
        self.assertNotIn("Daily session", filtered_page)

    def test_five_entries_per_page_and_next_navigation(self):
        rows = [
            transaction(idx, "products", f"Product number {idx}")
            for idx in range(1, 7)
        ]
        display, _ = self.run_screen(rows, [">", "0"])
        first, last = display.split("SCREEN: SEARCH TRANSACTIONS")[1:]
        self.assertIn("Page: 1 of 2", first)
        self.assertIn("R-000005", first)
        self.assertNotIn("R-000006", first)
        self.assertIn("Page: 2 of 2", last)
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
            patch("builtins.input", side_effect=["5", "water", "0", "0", "0"]),
            redirect_stdout(io.StringIO()),
        ):
            main.search_transactions_ui()
        self.assertEqual(calls, [
            None, None, {"query": "water"}, None, None
        ])

    def test_zero_restores_previous_search_before_leaving(self):
        rows = [transaction(1, "products", "Bottled water")]
        history, requests = self.run_screen(
            rows, ["water", "0", "0"]
        )
        views = history.split("SCREEN: SEARCH TRANSACTIONS")[1:]
        self.assertEqual(len(views), 3)
        self.assertIn("Search: water", views[1])
        self.assertNotIn("Search: water", views[2])
        self.assertIn("[0] Previous View", views[1])
        self.assertIn("[0] Back to Search Records", views[2])
        self.assertEqual(
            [call.kwargs.get("params") for call in requests.call_args_list],
            [None, {"query": "water"}, None],
        )

    def test_zero_restores_previous_category_and_query(self):
        rows = [
            transaction(1, "monthly", "Monthly Session"),
            transaction(2, "products", "Bottled water"),
        ]
        result, _ = self.run_screen(rows, ["2", "monthly", "0", "0", "0"])
        views = result.split("SCREEN: SEARCH TRANSACTIONS")[1:]
        self.assertEqual(len(views), 5)
        self.assertIn("Category: Monthly Session", views[1])
        self.assertIn("Search: monthly", views[2])
        self.assertIn("Category: Monthly Session", views[3])
        self.assertNotIn("Search: monthly", views[3])
        self.assertIn("Category: All Transactions", views[4])

    def test_shared_table_has_aligned_spaced_columns(self):
        columns = [
            ("ID", "id", 4),
            ("Product Name", "name", 25),
            ("Price", "price", 8, "right"),
        ]
        record = {
            "id": 1,
            "name": "Premium Whey Protein Powder, 2 kilograms",
            "price": "1800.00",
        }
        stream = io.StringIO()
        with redirect_stdout(stream):
            main.print_table_header(columns)
            main.print_table_row(record, columns)
        lines = stream.getvalue().splitlines()
        self.assertIn("  |  ", lines[0])
        self.assertEqual(len(lines[0]), main.table_width(columns))
        self.assertEqual(len(lines[1]), len(lines[0]))
        self.assertIn("kilograms", stream.getvalue())

    def test_page_nav_options_use_angle_brackets(self):
        self.assertEqual(
            main.page_nav_options(2, 3),
            "[>] Next        [<] Previous        [0] Back",
        )


if __name__ == "__main__":
    unittest.main()
