"""Shared table spacing keeps records distinct without splitting wrapped cells."""
import io
import unittest
from contextlib import redirect_stdout

import main


class TableSpacingTests(unittest.TestCase):
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
