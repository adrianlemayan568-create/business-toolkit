import sqlite3
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from database.migrate import (
    migrate,
    create_verified_backup,
    CURRENT_SCHEMA_VERSION
)


class TestDatabaseMigration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "legacy.db"

        self.email = "first@example.com"
        self.password_hash = "test-password-hash"

        self.create_legacy_database()

    def tearDown(self):
        self.temp_dir.cleanup()

    def get_connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_legacy_database(self):
        connection = self.get_connection()

        try:
            connection.executescript("""
                CREATE TABLE expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    category TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    expense_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                INSERT INTO expenses (
                    id,
                    amount_cents,
                    category,
                    description,
                    expense_date
                )
                VALUES
                    (1, 25000, 'Transport', 'Bus fare', '2026-10-31'),
                    (2, 50000, 'Food', 'Lunch', '2026-10-31'),
                    (3, 75000, 'Education', 'Books', '2026-11-01');
            """)

            connection.execute("PRAGMA user_version = 0")
            connection.commit()

        finally:
            connection.close()

    # ==========================================
    # SUCCESSFUL MIGRATION
    # ==========================================

    def test_successful_migration(self):
        user_id = migrate(
            self.database_path,
            self.email,
            self.password_hash
        )

        self.assertEqual(user_id, 1)

        connection = self.get_connection()

        try:
            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            self.assertEqual(
                version,
                CURRENT_SCHEMA_VERSION
            )

            user = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()

            self.assertIsNotNone(user)
            self.assertEqual(user["email"], self.email)

            self.assertEqual(
                user["password_hash"],
                self.password_hash
            )

        finally:
            connection.close()

    # ==========================================
    # EXPENSE PRESERVATION
    # ==========================================

    def test_existing_expenses_are_preserved(self):
        migrate(
            self.database_path,
            self.email,
            self.password_hash
        )

        connection = self.get_connection()

        try:
            expenses = connection.execute(
                """
                SELECT id, amount_cents, category,
                       description, expense_date
                FROM expenses
                ORDER BY id
                """
            ).fetchall()

            self.assertEqual(len(expenses), 3)

            self.assertEqual(
                [row["id"] for row in expenses],
                [1, 2, 3]
            )

            self.assertEqual(
                [row["amount_cents"] for row in expenses],
                [25000, 50000, 75000]
            )

            self.assertEqual(
                [row["category"] for row in expenses],
                ["Transport", "Food", "Education"]
            )

        finally:
            connection.close()

    def test_all_existing_expenses_belong_to_first_user(self):
        user_id = migrate(
            self.database_path,
            self.email,
            self.password_hash
        )

        connection = self.get_connection()

        try:
            owners = connection.execute(
                "SELECT DISTINCT user_id FROM expenses"
            ).fetchall()

            self.assertEqual(len(owners), 1)
            self.assertEqual(owners[0]["user_id"], user_id)

        finally:
            connection.close()

    def test_expense_total_is_preserved(self):
        migrate(
            self.database_path,
            self.email,
            self.password_hash
        )

        connection = self.get_connection()

        try:
            total = connection.execute(
                "SELECT SUM(amount_cents) FROM expenses"
            ).fetchone()[0]

            self.assertEqual(total, 150000)

        finally:
            connection.close()

    # ==========================================
    # FOREIGN KEY INTEGRITY
    # ==========================================

    def test_foreign_key_integrity(self):
        migrate(
            self.database_path,
            self.email,
            self.password_hash
        )

        connection = self.get_connection()

        try:
            violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

            self.assertEqual(violations, [])

        finally:
            connection.close()

    # ==========================================
    # MIGRATION VERSION PROTECTION
    # ==========================================

    def test_second_migration_attempt_is_rejected(self):
        migrate(
            self.database_path,
            self.email,
            self.password_hash
        )

        with self.assertRaises(RuntimeError):
            migrate(
                self.database_path,
                self.email,
                self.password_hash
            )

    # ==========================================
    # INVALID LEGACY SCHEMA
    # ==========================================

    def test_missing_expenses_table_is_rejected(self):
        connection = self.get_connection()

        try:
            connection.execute("DROP TABLE expenses")
            connection.commit()

        finally:
            connection.close()

        with self.assertRaises(RuntimeError):
            migrate(
                self.database_path,
                self.email,
                self.password_hash
            )

    def test_unexpected_schema_is_rejected(self):
        connection = self.get_connection()

        try:
            connection.execute(
                "ALTER TABLE expenses ADD COLUMN unexpected TEXT"
            )
            connection.commit()

        finally:
            connection.close()

        with self.assertRaises(RuntimeError):
            migrate(
                self.database_path,
                self.email,
                self.password_hash
            )

    # ==========================================
    # TRANSACTION ROLLBACK
    # ==========================================

    def test_failed_migration_rolls_back_changes(self):
        connection = self.get_connection()

        try:
            connection.execute(
                """
                INSERT INTO expenses (
                    amount_cents,
                    category,
                    description,
                    expense_date
                )
                VALUES (
                    1000,
                    '',
                    'Invalid category',
                    '2026-11-01'
                )
                """
            )

            connection.commit()

        finally:
            connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            migrate(
                self.database_path,
                self.email,
                self.password_hash
            )

        connection = self.get_connection()

        try:
            tables = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

            self.assertIn("expenses", tables)
            self.assertNotIn("users", tables)

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            self.assertEqual(version, 0)

            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(expenses)"
                )
            }

            self.assertNotIn("user_id", columns)

            count = connection.execute(
                "SELECT COUNT(*) FROM expenses"
            ).fetchone()[0]

            self.assertEqual(count, 4)

        finally:
            connection.close()

    # ==========================================
    # BACKUP CREATION AND VERIFICATION
    # ==========================================

    def test_backup_contains_original_database(self):
        backup_path = create_verified_backup(
            self.database_path
        )

        self.assertTrue(backup_path.is_file())

        connection = sqlite3.connect(backup_path)

        try:
            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            self.assertEqual(integrity, "ok")

            count = connection.execute(
                "SELECT COUNT(*) FROM expenses"
            ).fetchone()[0]

            self.assertEqual(count, 3)

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            self.assertEqual(version, 0)

        finally:
            connection.close()

    def test_backup_preserves_original_expense_total(self):
        backup_path = create_verified_backup(
            self.database_path
        )

        connection = sqlite3.connect(backup_path)

        try:
            total = connection.execute(
                "SELECT SUM(amount_cents) FROM expenses"
            ).fetchone()[0]

            self.assertEqual(total, 150000)

        finally:
            connection.close()

    # ==========================================
    # BACKUP FAILURE PROTECTION
    # ==========================================

    def test_migration_stops_if_backup_creation_fails(self):
        with patch(
            "database.migrate.create_verified_backup",
            side_effect=OSError("Simulated backup failure")
        ):
            with self.assertRaises(OSError):
                migrate(
                    self.database_path,
                    self.email,
                    self.password_hash
                )

        connection = self.get_connection()

        try:
            tables = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

            self.assertIn("expenses", tables)
            self.assertNotIn("users", tables)

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            self.assertEqual(version, 0)

            count = connection.execute(
                "SELECT COUNT(*) FROM expenses"
            ).fetchone()[0]

            self.assertEqual(count, 3)

        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
