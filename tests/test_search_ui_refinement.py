"""Membership tables open immediately and keep status filters in place."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import main


def membership(idx, status):
    return dict(id=idx, customer_id=idx, customer_name=f'Member{idx}',
                start_date='2026-01-01', end_date='2026-12-31', status=status)


class NavigationTests(unittest.TestCase):
    def screen(self, plan, rows, commands):
        def fetch(method, path, params):
            self.assertEqual((method, path), ('GET', '/memberships'))
            self.assertEqual(params['plan'], plan)
            return [r for r in rows if params['status'] == 'all' or r['status'].lower() == params['status']]
        output = io.StringIO()
        with (patch.object(main, 'header', side_effect=lambda title, **kw: print('SCREEN:', title)),
              patch.object(main, 'request', side_effect=fetch), patch.object(main, 'pause'),
              patch('builtins.input', side_effect=commands), redirect_stdout(output)):
            main.browse_plan_memberships(plan)
        return output.getvalue().split('SCREEN: ')[1:]

    def test_both_plans_open_all_active_first_and_filter_inline(self):
        for plan in ['Yearly membership', 'Monthly session']:
            with self.subTest(plan=plan):
                views = self.screen(plan, [membership(1, 'Expired'), membership(2, 'Active')],
                                    ['1', '2', '3', '0'])
                self.assertEqual(len(views), 4)
                self.assertLess(views[0].index('Member2'), views[0].index('Member1'))
                self.assertIn('Member2', views[1])
                self.assertNotIn('Member1', views[1])
                self.assertIn('Member1', views[2])
                self.assertNotIn('Member2', views[2])
                self.assertIn('Member1', views[3])
                self.assertIn('Member2', views[3])
                for view in views:
                    self.assertIn('[0] Back', view)
                    self.assertNotIn('[B] Back', view)

    def test_page_controls_only_above_ten_and_filter_resets_page(self):
        for count in [0, 10, 11]:
            for plan in ['Yearly membership', 'Monthly session']:
                with self.subTest(count=count, plan=plan):
                    rows = [membership(i, 'Active') for i in range(1, count + 1)]
                    commands = ['>', '<', '>', '2', '3', '0'] if count > 10 else ['2', '3', '0']
                    views = self.screen(plan, rows, commands)
                    self.assertEqual('[>] Next' in views[0], count > 10)
                    self.assertEqual('[<] Previous' in views[0], count > 10)
                    if count > 10:
                        self.assertNotIn('Member11', views[0])
                        self.assertIn('Member11', views[1])
                        self.assertNotIn('Member11', views[2])
                    self.assertIn('No ', views[-2])
                    self.assertIn('[3] All', views[-2])
                    self.assertNotIn('[>] Next', views[-2])
                    self.assertIn('Page 1 of', views[-1])
