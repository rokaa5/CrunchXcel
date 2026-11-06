"""Shared table spacing keeps records distinct without splitting wrapped cells."""
import io
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

import main


class TableSpacingTests(unittest.TestCase):
    def test_select_active_member_only_uses_compact_spacing(self):
        customer = dict(id=3, first_name='Yearly', last_name='Member',
                        yearly_status='Active', yearly_end_date='2027-11-07')
        output = io.StringIO()
        with (patch.object(main, 'header'),
              patch.object(main, 'request', return_value=[customer]),
              patch('builtins.input', side_effect=['1', '3']), redirect_stdout(output)):
            result = main.select_sale_customer('DAILY SESSION')
        self.assertEqual(result[0], 3)
        lines = output.getvalue().splitlines()
        heading = next(i for i, line in enumerate(lines) if 'Expires' in line)
        self.assertTrue(lines[heading + 1].startswith('---'))
        self.assertIn('Yearly Member', lines[heading + 2])
        self.assertTrue(lines[heading + 3].startswith('---'))

    def test_header_and_records_have_vertical_space(self):
        columns = [('ID', 'id', 4), ('Name', 'name', 12)]
        output = io.StringIO()
        with redirect_stdout(output):
            print('Records: 2')
            main.print_table_header(columns)
            main.print_table_row({'id': 1, 'name': 'David'}, columns)
            main.print_table_row({'id': 2, 'name': 'Dave'}, columns)
            print('[0] Back')
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[1], '')
        self.assertEqual(lines[3], '')
        self.assertEqual(lines[5], '')
        self.assertEqual(lines[7], '')
        self.assertIn('David', lines[4])
        self.assertIn('Dave', lines[6])
        self.assertEqual(len(lines[2]), main.table_width(columns))
        self.assertEqual(len(lines[4]), len(lines[2]))

    def test_wrapped_record_stays_together_and_keeps_numeric_alignment(self):
        columns = [('Name', 'name', 6), ('Amount', 'amount', 8, 'right')]
        output = io.StringIO()
        with redirect_stdout(output):
            main.print_table_row({'name': 'Long item name', 'amount': '12.00'}, columns)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn('Long', lines[0])
        self.assertTrue(lines[0].endswith('   12.00'))
        self.assertIn('item', lines[1])
        self.assertIn('name', lines[2])
        self.assertEqual(lines[3], '')
