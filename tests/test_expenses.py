
import unittest
import sqlite3
import tempfile
import csv
import io

from pathlib import Path
from unittest.mock import patch

from modules import expenses


class TestExpenses(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.temp_dir.name) / "test.db"

        self.connection = sqlite3.connect(self.test_db)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

        self.connection.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                expense_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            INSERT INTO users (id, email, password_hash)
            VALUES
                (1, 'alice@example.com', 'test-hash'),
                (2, 'bob@example.com', 'test-hash');
        """)

        self.connection.commit()
        self.connection.close()

        self.patcher = patch(
            "modules.expenses.get_connection",
            self.get_test_connection
        )
        self.patcher.start()

        self.user1 = 1
        self.user2 = 2

    def get_test_connection(self):
        connection = sqlite3.connect(self.test_db)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    # ------------------------------------------
    # BASIC EXPENSE TESTS
    # ------------------------------------------

    def test_add_expense(self):
        result = expenses.add_expense(
            self.user1, 100, "Food", "Lunch", "2026-11-01"
        )

        self.assertTrue(result)

        records = expenses.view_expenses(self.user1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount_cents"], 10000)

    def test_reject_zero_amount(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, 0, "Food")

    def test_reject_negative_amount(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, -100, "Food")

    def test_reject_invalid_date(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(
                self.user1, 100, "Food", "Lunch", "invalid-date"
            )

    def test_calculate_total(self):
        expenses.add_expense(self.user1, 100, "Food")
        expenses.add_expense(self.user1, 200, "Transport")

        self.assertEqual(
            expenses.get_total_expenses(self.user1),
            30000
        )

    def test_delete_existing_expense(self):
        expenses.add_expense(self.user1, 100, "Food")

        records = expenses.view_expenses(self.user1)
        expense_id = records[0]["id"]

        self.assertTrue(
            expenses.delete_expense(self.user1, expense_id)
        )

        self.assertEqual(
            len(expenses.view_expenses(self.user1)),
            0
        )

    def test_delete_nonexistent_expense(self):
        self.assertFalse(
            expenses.delete_expense(self.user1, 999)
        )

    def test_reject_empty_category(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, 100, "   ")

    def test_reject_amount_with_more_than_two_decimal_places(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, 100.999, "Food")

    def test_reject_invalid_expense_id(self):
        with self.assertRaises(ValueError):
            expenses.delete_expense(self.user1, -1)

    def test_reject_invalid_user_ids(self):
        for invalid_id in (0, -1, "1", True, None):
            with self.subTest(user_id=invalid_id):
                with self.assertRaises(ValueError):
                    expenses.view_expenses(invalid_id)

    # ------------------------------------------
    # ACCOUNT OWNERSHIP / ISOLATION TESTS
    # ------------------------------------------

    def test_users_cannot_see_each_others_expenses(self):
        expenses.add_expense(self.user1, 100, "Alice expense")
        expenses.add_expense(self.user2, 200, "Bob expense")

        alice_records = expenses.view_expenses(self.user1)
        bob_records = expenses.view_expenses(self.user2)

        self.assertEqual(len(alice_records), 1)
        self.assertEqual(len(bob_records), 1)

        self.assertEqual(
            alice_records[0]["category"],
            "Alice expense"
        )

        self.assertEqual(
            bob_records[0]["category"],
            "Bob expense"
        )

    def test_users_cannot_read_another_users_expense_by_id(self):
        expense_id = expenses.add_expense(
            self.user1, 100, "Private expense"
        )

        result = expenses.get_expense(self.user2, expense_id)

        self.assertIsNone(result)

    def test_users_cannot_update_another_users_expense(self):
        expense_id = expenses.add_expense(
            self.user1, 100, "Alice expense"
        )

        result = expenses.update_expense(
            self.user2,
            expense_id,
            500,
            "Changed by Bob"
        )

        self.assertFalse(result)

        original = expenses.get_expense(self.user1, expense_id)

        self.assertEqual(original["amount_cents"], 10000)
        self.assertEqual(original["category"], "Alice expense")

    def test_users_cannot_delete_another_users_expense(self):
        expense_id = expenses.add_expense(
            self.user1, 100, "Alice expense"
        )

        result = expenses.delete_expense(
            self.user2,
            expense_id
        )

        self.assertFalse(result)

        original = expenses.get_expense(self.user1, expense_id)

        self.assertIsNotNone(original)
        self.assertEqual(original["category"], "Alice expense")

    def test_totals_are_separated_by_user(self):
        expenses.add_expense(self.user1, 100, "Food")
        expenses.add_expense(self.user1, 200, "Transport")
        expenses.add_expense(self.user2, 900, "Rent")

        self.assertEqual(
            expenses.get_total_expenses(self.user1),
            30000
        )

        self.assertEqual(
            expenses.get_total_expenses(self.user2),
            90000
        )

    def test_csv_export_contains_only_current_users_expenses(self):
        expenses.add_expense(
            self.user1, 100, "Alice expense", "Private"
        )

        expenses.add_expense(
            self.user2, 900, "Bob secret", "Not Alice's"
        )

        content = expenses.export_expenses(self.user1)
        rows = list(csv.reader(io.StringIO(content)))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], "Alice expense")
        self.assertNotIn("Bob secret", content)

    # ------------------------------------------
    # CSV EXPORT TESTS
    # ------------------------------------------

    def test_export_expenses(self):
        expenses.add_expense(
            self.user1, 150.50, "Food", "Lunch", "2026-11-01"
        )

        expenses.add_expense(
            self.user1, 200, "Transport", "Bus fare", "2026-11-01"
        )

        content = expenses.export_expenses(self.user1)
        rows = list(csv.reader(io.StringIO(content)))

        self.assertEqual(
            rows[0],
            ["ID", "Amount (KSh)", "Category", "Description", "Date"]
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][1], "200.00")
        self.assertEqual(rows[1][2], "Transport")
        self.assertEqual(rows[2][1], "150.50")
        self.assertEqual(rows[2][2], "Food")

    def test_safe_csv_text_protects_formula_prefixes(self):
        dangerous_values = [
            "=SUM(1+1)",
            "+123",
            "-123",
            "@SUM(A1:A2)"
        ]

        for value in dangerous_values:
            with self.subTest(value=value):
                self.assertEqual(
                    expenses.safe_csv_text(value),
                    "'" + value
                )

    def test_safe_csv_text_protects_leading_whitespace(self):
        dangerous_values = [
            " =SUM(1+1)",
            "\t=SUM(1+1)",
            "\n=SUM(1+1)",
            "   +123",
            "\t-123",
            " @SUM(A1:A2)"
        ]

        for value in dangerous_values:
            with self.subTest(value=value):
                self.assertEqual(
                    expenses.safe_csv_text(value),
                    "'" + value
                )

    def test_safe_csv_text_protects_leading_control_characters(self):
        for value in ("\tHello", "\rHello", "\nHello"):
            with self.subTest(value=value):
                self.assertEqual(
                    expenses.safe_csv_text(value),
                    "'" + value
                )

    def test_safe_csv_text_preserves_ordinary_text(self):
        ordinary_values = [
            "Food",
            "Lunch",
            "Bus fare",
            "Monthly rent",
            "",
            "123",
            "Food + transport"
        ]

        for value in ordinary_values:
            with self.subTest(value=value):
                self.assertEqual(
                    expenses.safe_csv_text(value),
                    value
                )

    def test_csv_export_sanitizes_malicious_text(self):
        expenses.add_expense(
            self.user1,
            100,
            "=SUM(A1:A2)",
            "+CMD"
        )

        rows = list(
            csv.reader(
                io.StringIO(expenses.export_expenses(self.user1))
            )
        )

        self.assertEqual(rows[1][2], "'=SUM(A1:A2)")
        self.assertEqual(rows[1][3], "'+CMD")
        self.assertEqual(rows[1][1], "100.00")

    def test_csv_export_preserves_normal_text(self):
        expenses.add_expense(
            self.user1, 100, "Food", "Lunch"
        )

        rows = list(
            csv.reader(
                io.StringIO(expenses.export_expenses(self.user1))
            )
        )

        self.assertEqual(rows[1][2], "Food")
        self.assertEqual(rows[1][3], "Lunch")

    # ------------------------------------------
    # MONTHLY REPORT TESTS
    # ------------------------------------------

    def test_monthly_category_totals(self):
        expenses.add_expense(self.user1, 100, "Food", "", "2026-11-01")
        expenses.add_expense(self.user1, 200, "Transport", "", "2026-11-02")
        expenses.add_expense(self.user1, 150, "Food", "", "2026-11-03")
        expenses.add_expense(self.user1, 500, "Rent", "", "2026-10-15")

        results = expenses.get_monthly_category_totals(
            self.user1, 2026, 11
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["category"], "Food")
        self.assertEqual(results[0]["total_cents"], 25000)
        self.assertEqual(results[1]["category"], "Transport")
        self.assertEqual(results[1]["total_cents"], 20000)

    def test_monthly_expenses_decrease(self):
        expenses.add_expense(
            self.user1, 3500, "Transport", "October", "2026-10-15"
        )
        expenses.add_expense(
            self.user1, 2800, "Transport", "November", "2026-11-15"
        )

        result = expenses.compare_monthly_expenses(
            self.user1, 2026, 10, 2026, 11
        )

        self.assertEqual(result["first_month_total"], 350000)
        self.assertEqual(result["second_month_total"], 280000)
        self.assertEqual(result["difference"], -70000)
        self.assertAlmostEqual(result["percentage_change"], -20.0)

    def test_monthly_expenses_increase(self):
        expenses.add_expense(
            self.user1, 2000, "Food", "October", "2026-10-15"
        )
        expenses.add_expense(
            self.user1, 3000, "Food", "November", "2026-11-15"
        )

        result = expenses.compare_monthly_expenses(
            self.user1, 2026, 10, 2026, 11
        )

        self.assertEqual(result["difference"], 100000)
        self.assertAlmostEqual(result["percentage_change"], 50.0)

    def test_monthly_comparison_with_zero_first_month(self):
        expenses.add_expense(
            self.user1, 1000, "Food", "November", "2026-11-15"
        )

        result = expenses.compare_monthly_expenses(
            self.user1, 2026, 10, 2026, 11
        )

        self.assertEqual(result["first_month_total"], 0)
        self.assertEqual(result["second_month_total"], 100000)
        self.assertIsNone(result["percentage_change"])

    # ------------------------------------------
    # EXPENSE UPDATE TESTS
    # ------------------------------------------

    def test_update_existing_expense(self):
        expense_id = expenses.add_expense(
            self.user1, 100, "Food", "Lunch", "2026-11-01"
        )

        result = expenses.update_expense(
            self.user1,
            expense_id,
            250.50,
            "Transport",
            "Bus fare",
            "2026-11-02"
        )

        self.assertTrue(result)

        records = expenses.view_expenses(self.user1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], expense_id)
        self.assertEqual(records[0]["amount_cents"], 25050)
        self.assertEqual(records[0]["category"], "Transport")
        self.assertEqual(records[0]["description"], "Bus fare")
        self.assertEqual(records[0]["expense_date"], "2026-11-02")

    def test_update_nonexistent_expense(self):
        result = expenses.update_expense(
            self.user1, 999, 100, "Food", "Lunch", "2026-11-01"
        )

        self.assertFalse(result)

    def test_update_rejects_zero_amount(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")

        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, 0, "Food"
            )

    def test_update_rejects_negative_amount(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")

        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, -50, "Food"
            )

    def test_update_rejects_more_than_two_decimal_places(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")

        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, 100.999, "Food"
            )

    def test_update_rejects_empty_category(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")

        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, 150, "   "
            )

    def test_update_rejects_invalid_date(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")

        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, 150, "Food", "Lunch", "invalid-date"
            )

    def test_update_rejects_invalid_expense_id(self):
        for invalid_id in (0, -1, "1", True):
            with self.subTest(expense_id=invalid_id):
                with self.assertRaises(ValueError):
                    expenses.update_expense(
                        self.user1, invalid_id, 150, "Food"
                    )


    # ------------------------------------------
    # INPUT LIMIT TESTS
    # ------------------------------------------

    def test_add_accepts_maximum_amount(self):
        expense_id = expenses.add_expense(
            self.user1, "999999999.99", "Food"
        )
        record = expenses.get_expense(self.user1, expense_id)
        self.assertEqual(record["amount_cents"], 99999999999)

    def test_add_rejects_amount_above_maximum(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, "1000000000.00", "Food")

    def test_add_rejects_category_over_50_characters(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, 100, "A" * 51)

    def test_add_accepts_category_of_50_characters(self):
        expense_id = expenses.add_expense(self.user1, 100, "A" * 50)
        record = expenses.get_expense(self.user1, expense_id)
        self.assertEqual(len(record["category"]), 50)

    def test_add_rejects_description_over_500_characters(self):
        with self.assertRaises(ValueError):
            expenses.add_expense(self.user1, 100, "Food", "D" * 501)

    def test_add_rejects_non_text_fields(self):
        for category, description in (
            (None, ""), (123, ""), ("Food", None), ("Food", 123)
        ):
            with self.subTest(category=category, description=description):
                with self.assertRaises(ValueError):
                    expenses.add_expense(
                        self.user1, 100, category, description
                    )

    def test_update_rejects_amount_above_maximum(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")
        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, "1000000000.00", "Food"
            )

    def test_update_rejects_category_over_50_characters(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")
        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, 100, "A" * 51
            )

    def test_update_rejects_description_over_500_characters(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")
        with self.assertRaises(ValueError):
            expenses.update_expense(
                self.user1, expense_id, 100, "Food", "D" * 501
            )

    def test_update_rejects_non_text_fields(self):
        expense_id = expenses.add_expense(self.user1, 100, "Food")
        for category, description in (
            (None, ""), (123, ""), ("Food", None), ("Food", 123)
        ):
            with self.subTest(category=category, description=description):
                with self.assertRaises(ValueError):
                    expenses.update_expense(
                        self.user1, expense_id, 100, category, description
                    )


if __name__ == "__main__":
    unittest.main()
