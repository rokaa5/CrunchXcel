import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main
from test_compact_transactions_ui import transaction


class CompactNavigationTests(unittest.TestCase):
    def test_registration_and_renewal_use_compact_tables_for_both_plans(self):
        customer = dict(id=1, first_name='David', last_name='Domingo', phone='09191234567')
        for plan in ['Yearly membership', 'Monthly session']:
            for function in [main.register_plan, main.renew_plan]:
                with self.subTest(plan=plan, function=function.__name__):
                    output = io.StringIO()
                    commands = ['1', '0', '0'] if function == main.register_plan else ['0']
                    with (patch.object(main, 'header'), patch.object(main, 'request', return_value=[customer]),
                          patch('builtins.input', side_effect=commands), redirect_stdout(output)):
                        function(plan)
                    lines = output.getvalue().splitlines()
                    row = next(i for i, line in enumerate(lines) if 'David Domingo' in line)
                    self.assertTrue(lines[row - 1].startswith('---'))
                    self.assertTrue(lines[row + 1].startswith('---'))
                    footer = next(line for line in lines if 'Showing' in line)
                    self.assertIn('[0] Back', footer)

    def test_long_controls_wrap_to_terminal_width_without_losing_options(self):
        output = io.StringIO()
        with (patch.object(main.shutil, 'get_terminal_size', return_value=os.terminal_size((50, 24))),
              redirect_stdout(output)):
            main.print_controls('[S] Search by customer, item, or receipt    [<] Previous page    [>] Next page    [C] Clear search    [0] Back', 130)
        lines = output.getvalue().splitlines()
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 50 for line in lines))
        self.assertIn('[0] Back', ' '.join(lines))

    def test_compact_selection_footer_keeps_back_with_page_count(self):
        output = io.StringIO()
        with patch.object(main, 'header'), redirect_stdout(output):
            main.render_data_table('SELECT', [dict(id=1)], [('ID', 'id', 4)],
                                   1, width=90, always_show_back=True, compact=True)
        footer = next(line for line in output.getvalue().splitlines() if 'Showing' in line)
        self.assertIn('[0] Back', footer)

    def test_refund_ten_row_boundary_and_horizontal_controls(self):
        for count in [0, 10, 11]:
            with self.subTest(count=count):
                output = io.StringIO()
                rows = [transaction(i, 'products', 'Water') for i in range(1, count + 1)]
                with (patch.object(main, 'header', side_effect=lambda *a, **kw: print('SCREEN')),
                      patch.object(main, 'request', return_value=rows),
                      patch('builtins.input', side_effect=['>', '0'] if count > 10 else ['0']),
                      redirect_stdout(output)):
                    main.refund_purchase_session()
                views = output.getvalue().split('SCREEN')[1:]
                self.assertEqual('[>] Next' in views[0], count > 10)
                self.assertEqual('[<] Previous' in views[0], count > 10)
                control_lines = views[0][views[0].index('[S]'):].splitlines()
                self.assertIn('[0] Back', ' '.join(control_lines))
                self.assertNotIn('\n[0] Back', views[0])
                if count > 10:
                    self.assertIn('R-000010', views[0])
                    self.assertNotIn('R-000011', views[0])
                    self.assertIn('R-000011', views[1])
                lines = views[0].splitlines()
                row_index = next((i for i, line in enumerate(lines) if 'R-000001' in line), None)
                if row_index is not None:
                    self.assertNotEqual(lines[row_index + 1], '')
