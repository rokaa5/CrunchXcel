"""Regression tests for consolidated browsing and category-first search."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main


class NavigationTests(unittest.TestCase):
    def test_membership_filter_selection(self):
        with (
            patch.object(main, "header"),
            patch.object(main, "view_plan_memberships") as view,
            patch("builtins.input", side_effect=["1", "2", "0", "b"]),
            redirect_stdout(io.StringIO()),
        ):
            main.browse_plan_memberships("Yearly membership")
        self.assertEqual(
            [call.args[1] for call in view.call_args_list],
            ["active", "expired", "all"],
        )

    def test_customer_search_matches_either_name_and_id(self):
        customers = [
            {"id": 1, "first_name": "David", "last_name": "Domingo", "phone": ""},
            {"id": 2, "first_name": "David", "last_name": "Santos", "phone": ""},
        ]
        for query, expected in [
            ("David", [1, 2]),
            ("Domingo", [1]),
            ("David Domingo", [1]),
            ("2", [2]),
        ]:
            with self.subTest(query=query):
                captured = []
                def display(*args, **kwargs):
                    captured.extend(args[1]())
                with (
                    patch.object(main, "header"),
                    patch.object(main, "request", return_value=customers),
                    patch.object(main, "paginated_view", side_effect=display),
                    patch("builtins.input", return_value=query),
                    redirect_stdout(io.StringIO()),
                ):
                    main.search_customer()
                self.assertEqual([r["id"] for r in captured], expected)

    def test_transaction_category_selection_precedes_search(self):
        records = [{
            "reference": "R-000001", "record_type": "sale",
            "record_id": 1, "created_at": "2026-11-07 01:00:00",
            "item_names": "Bottled water", "amount": "10.00",
            "status": "Completed", "categories": ["products"],
        }]
        choices = iter(["5", "s", "Bottled", "0", "0"])
        with (
            patch.object(main, "header"),
            patch.object(main, "request", return_value=records),
            patch("builtins.input", side_effect=lambda *a: next(choices)),
            redirect_stdout(io.StringIO()),
        ):
            main.search_transactions_ui()


if __name__ == "__main__":
    unittest.main()
