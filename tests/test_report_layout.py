"""Customer separators and daily report footer layout."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main


class ReportLayoutTests(unittest.TestCase):
    def test_customer_metadata_is_separated_from_column_headings(self):
        output = io.StringIO()
        with (patch.object(main, 'header'), patch.object(main, 'request', return_value=[]),
              patch('builtins.input', return_value='0'), redirect_stdout(output)):
            main.search_customer()
        lines = [line for line in output.getvalue().splitlines() if line]
        self.assertIn('Records: 0', lines[0])
        self.assertEqual(lines[1], '-' * 90)
        self.assertIn('First Name', lines[2])

    def test_daily_totals_follow_table_on_every_page(self):
        for count in [1, 11]:
            with self.subTest(count=count):
                sample = [{'period': '2026-11-07', 'gross_sales': '120.00',
                           'refunds_total': '20.00', 'transactions': [
                               dict(receipt_no=f'R-{i:06}', time='02:55', item_name='Water',
                                    total='10.00', status='Completed') for i in range(count)]}]
                output = io.StringIO()
                with (patch.object(main, 'request', return_value=sample),
                      patch.object(main, 'header', side_effect=lambda *a, **kw: print('SCREEN')),
                      patch.object(main, 'pause', side_effect=lambda: print('PAUSE')),
                      patch('builtins.input', side_effect=['>', '0']), redirect_stdout(output)):
                    main.daily_transactions()
                pages = output.getvalue().split('SCREEN')[1:]
                self.assertEqual(len(pages), 1 if count == 1 else 2)
                for page in pages:
                    self.assertLess(page.rindex('R-'), page.index('Gross Sales:'))
                    self.assertIn('Gross Sales:       120.00', page)
                    self.assertIn('Refunds Issued:    -20.00', page)
                    self.assertIn('Net Sales:         100.00', page)
                    footer_end = page.index('Net Sales:')
                    self.assertLess(footer_end, page.index('PAUSE') if count == 1 else page.index('[0] Back'))
