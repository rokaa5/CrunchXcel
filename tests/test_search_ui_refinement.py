"""Regression tests for consolidated membership browsing."""
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



if __name__ == "__main__":
    unittest.main()
