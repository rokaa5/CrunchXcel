import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main
from test_compact_transactions_ui import transaction


class ImmediateSearchTests(unittest.TestCase):
    def screen(self, function, records, commands):
        output = io.StringIO()
        with (patch.object(main, 'header', side_effect=lambda title, **kw: print('SCREEN:', title)),
              patch.object(main, 'request', return_value=records),
              patch.object(main, 'pause'),
              patch('builtins.input', side_effect=commands), redirect_stdout(output)):
            function()
        return output.getvalue().split('SCREEN: ')[1:]

    def test_transactions_open_all_and_switch_every_category_in_place(self):
        rows = [transaction(i, category, label) for i, category, label in [
            (1, 'yearly', 'Annual pass'), (2, 'monthly', 'Month pass'),
            (3, 'daily', 'Day pass'), (4, 'trainer', 'Coaching'),
            (5, 'products', 'Water')]]
        views = self.screen(main.search_transactions_ui, rows, ['1', '2', '3', '4', '5', '6', '0'])
        self.assertEqual(len(views), 7)
        for label in ['Annual pass', 'Month pass', 'Day pass', 'Coaching', 'Water']:
            self.assertIn(label, views[0])
            self.assertIn(label, views[-1])
        for index, label in enumerate(['Annual pass', 'Month pass', 'Day pass', 'Coaching', 'Water'], 1):
            self.assertIn(label, views[index])
            self.assertEqual(views[index].count('R-00000'), 1)

    def test_customer_partial_matching_and_clear(self):
        rows = [dict(id=i, first_name=first, last_name=last, phone='') for i, first, last in [
            (1, 'Dave', 'Smith'), (10, 'David', 'Domingo'), (21, 'Davro', 'Jones'),
            (2, 'Alice', 'DAVIS'), (3, 'Bob', 'Brown')]]
        views = self.screen(main.search_customer, rows, ['1', 'DaV', '  DAVID   domingo ', 'missing', 'c', '0'])
        self.assertEqual(len(views), 6)
        self.assertIn('Bob', views[0])
        for name in ['Dave', 'David', 'Davro']:
            self.assertIn(name, views[1])
        self.assertNotIn('Alice', views[1])
        self.assertIn('Alice', views[2])
        self.assertNotIn('Bob', views[2])
        self.assertIn('David', views[3])
        self.assertNotIn('Dave', views[3])
        self.assertIn('No matching customers', views[4])
        self.assertIn('Bob', views[5])
        self.assertNotIn('Examples:', ''.join(views))

    def test_pagination_boundaries_for_both_screens(self):
        for count in [0, 1, 10, 11, 21]:
            for function in [main.search_customer, main.search_transactions_ui]:
                with self.subTest(count=count, function=function.__name__):
                    rows = [transaction(i, 'products', f'Product {i}') if function == main.search_transactions_ui
                            else dict(id=i, first_name=f'Person{i}', last_name='Member', phone='')
                            for i in range(1, count + 1)]
                    views = self.screen(function, rows, ['>', '<', '0'] if count > 10 else ['0'])
                    self.assertEqual('[>] Next' in views[0], count > 10)
                    self.assertEqual('[<] Previous' in views[0], count > 10)
                    if count > 10:
                        marker = 'R-000011' if function == main.search_transactions_ui else 'Person11'
                        self.assertNotIn(marker, views[0])
                        self.assertIn(marker, views[1])
                        self.assertNotIn(marker, views[2])

    def test_transaction_search_cancel_clear_and_receipt_keep_category(self):
        rows = [transaction(1, 'products', 'Water'), transaction(2, 'monthly', 'Month pass')]
        with patch.object(main, 'view_sale_details') as details:
            views = self.screen(main.search_transactions_ui, rows,
                                ['5', 's', 'Water', 's', '0', 'R-000001', 'c', '0'])
        details.assert_called_once_with(1)
        self.assertIn('Search: Water', views[2])
        self.assertIn('Search: Water', views[3])
        self.assertNotIn('Search: Water', views[-1])
        for view in views[1:]:
            self.assertNotIn('Month pass', view)

    def test_customer_search_resets_page_and_uses_filtered_count(self):
        rows = [dict(id=i, first_name=f'Person{i}', last_name='Member', phone='')
                for i in range(1, 22)]
        views = self.screen(main.search_customer, rows, ['>', 'Person21', '', '0'])
        self.assertIn('Page 2 of 3', views[1])
        self.assertIn('Records: 1    Page 1 of 1', views[2])
        self.assertIn('Person21', views[2])
        self.assertNotIn('[>] Next', views[2])
        self.assertIn('Records: 21    Page 1 of 3', views[3])

    def test_category_switch_resets_page_and_search_uses_filtered_count(self):
        rows = [transaction(i, 'products', f'Product {i}') for i in range(1, 22)]
        with patch.object(main, 'request', side_effect=[rows, rows, rows, rows[-1:]]):
            output = io.StringIO()
            with (patch.object(main, 'header', side_effect=lambda title, **kw: print('SCREEN:', title)),
                  patch('builtins.input', side_effect=['>', '5', 's', 'Product 21', '0']),
                  redirect_stdout(output)):
                main.search_transactions_ui()
        views = output.getvalue().split('SCREEN: ')[1:]
        self.assertIn('Page 2 of 3', views[1])
        self.assertIn('Page 1 of 3', views[2])
        self.assertIn('Records: 1    Page 1 of 1', views[3])
        self.assertIn('R-000021', views[3])
        self.assertNotIn('[>] Next', views[3])
