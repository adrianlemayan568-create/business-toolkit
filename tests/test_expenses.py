import unittest
import sqlite3
import tempfile
import csv
from pathlib import Path
from unittest.mock import patch

from modules import expenses


class TestExpenses(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.temp_dir.name) / "test.db"

        self.connection = sqlite3.connect(self.test_db)
        self.connection.row_factory = sqlite3.Row

        self.connection.execute("""
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                expense_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.connection.commit()
        self.connection.close()

        self.patcher = patch(
            "modules.expenses.get_connection",
            self.get_test_connection
        )
        self.patcher.start()

    def get_test_connection(self):
        connection = sqlite3.connect(self.test_db)
        connection.row_factory = sqlite3.Row
        return connection

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_add_expense(self):
        result = expenses.add_expense(
            100, "Food", "Lunch", "2026-11-01"
        )
        self.assertTrue(result)

        records = expenses.view_expenses()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount_cents"], 10000)

    def test_reject_zero_amount(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(0, "Food")

    def test_reject_negative_amount(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(-100, "Food")

    def test_reject_invalid_date(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(
                100, "Food", "Lunch", "invalid-date"
            )

    def test_calculate_total(self):
        expenses.add_expense(100, "Food", "", "2026-11-01")
        expenses.add_expense(200, "Transport", "", "2026-11-01")

        self.assertEqual(expenses.get_total_expenses(), 30000)

    def test_delete_existing_expense(self):
        expenses.add_expense(100, "Food", "", "2026-11-01")

        records = expenses.view_expenses()
        expense_id = records[0]["id"]

        self.assertTrue(expenses.delete_expense(expense_id))
        self.assertEqual(len(expenses.view_expenses()), 0)

    def test_delete_nonexistent_expense(self):
        self.assertFalse(expenses.delete_expense(999))

    def test_reject_empty_category(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(100, "   ")

    def test_reject_amount_with_more_than_two_decimal_places(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(100.999, "Food")

    def test_reject_invalid_expense_id(self):
        self.assertFalse(expenses.delete_expense(-1))

    def test_export_expenses(self):
        expenses.add_expense(
            150.50, "Food", "Lunch", "2026-11-01"
        )

        expenses.add_expense(
            200, "Transport", "Bus fare", "2026-11-01"
        )

        test_export_dir = Path(self.temp_dir.name) / "exports"

        with patch(
            "pathlib.Path.resolve",
            return_value=test_export_dir / "fake_module.py"
        ):
            export_path = expenses.export_expenses()

        self.assertTrue(export_path.exists())

        with open(export_path, "r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            rows = list(reader)

        self.assertEqual(
            rows[0],
            ["ID", "Amount (KSh)", "Category", "Description", "Date"]
        )

        self.assertEqual(len(rows), 3)

        self.assertEqual(rows[1][1], "200.00")
        self.assertEqual(rows[1][2], "Transport")
        self.assertEqual(rows[1][3], "Bus fare")

        self.assertEqual(rows[2][1], "150.50")
        self.assertEqual(rows[2][2], "Food")
        self.assertEqual(rows[2][3], "Lunch")

    def test_monthly_category_totals(self):
        expenses.add_expense(
            100, "Food", "", "2026-11-01"
        )

        expenses.add_expense(
            200, "Transport", "", "2026-11-02"
        )

        expenses.add_expense(
            150, "Food", "", "2026-11-03"
        )

        expenses.add_expense(
            500, "Rent", "", "2026-10-15"
        )

        results = expenses.get_monthly_category_totals(2026, 11)

        self.assertEqual(len(results), 2)

        self.assertEqual(results[0]["category"], "Food")
        self.assertEqual(results[0]["total_cents"], 25000)

        self.assertEqual(results[1]["category"], "Transport")
        self.assertEqual(results[1]["total_cents"], 20000)

if __name__ == "__main__":
    unittest.main()
