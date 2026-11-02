import argparse
import getpass
import re
import sqlite3
import sys

from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = BASE_DIR / "database" / "business.db"

CURRENT_SCHEMA_VERSION = 1


def normalize_email(email):
    email = email.strip().lower()

    if len(email) > 254:
        raise ValueError("Email address is too long.")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address.")

    return email


def get_account_details():
    email = normalize_email(input("First account email: "))

    password = getpass.getpass(
        "Create password (minimum 12 characters): "
    )

    confirmation = getpass.getpass("Confirm password: ")

    if password != confirmation:
        raise ValueError("Passwords do not match.")

    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")

    if len(password) > 128:
        raise ValueError("Password is too long.")

    return email, generate_password_hash(password)


def validate_legacy_database(connection):
    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    if version != 0:
        raise RuntimeError(
            f"Expected schema version 0, found {version}."
        )

    tables = {
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        )
    }

    if "expenses" not in tables:
        raise RuntimeError("The expenses table does not exist.")

    if "users" in tables:
        raise RuntimeError(
            "A users table already exists. Migration stopped."
        )

    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(expenses)"
        )
    }

    required_columns = {
        "id",
        "amount_cents",
        "category",
        "description",
        "expense_date",
        "created_at"
    }

    if columns != required_columns:
        raise RuntimeError(
            "The existing expenses schema is not "
            "the expected legacy schema."
        )


def create_verified_backup(database_path):
    database_path = Path(database_path).resolve()

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    backup_path = database_path.with_name(
        f"{database_path.stem}.pre_migration_{timestamp}"
        f"{database_path.suffix}"
    )

    source = None
    destination = None

    try:
        # Exclusive creation prevents overwriting an existing backup.
        with backup_path.open("xb"):
            pass

        source = sqlite3.connect(
            database_path,
            timeout=10
        )

        destination = sqlite3.connect(
            backup_path,
            timeout=10
        )

        source.backup(destination)

        destination.commit()
        destination.close()
        destination = None

        source.close()
        source = None

        # Verify the backup independently.
        verification = sqlite3.connect(
            backup_path,
            timeout=10
        )

        try:
            integrity = verification.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if integrity != "ok":
                raise RuntimeError(
                    f"Backup integrity check failed: {integrity}"
                )

            foreign_key_errors = verification.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

            if foreign_key_errors:
                raise RuntimeError(
                    "Backup contains foreign-key violations."
                )

        finally:
            verification.close()

        return backup_path

    except Exception:
        if destination is not None:
            destination.close()

        if source is not None:
            source.close()

        # Remove only an incomplete backup.
        if backup_path.exists():
            backup_path.unlink()

        raise


def migrate(database_path, email, password_hash):
    database_path = Path(database_path).resolve()

    if not database_path.is_file():
        raise RuntimeError(
            f"Database file not found: {database_path}"
        )

    # Validate before creating a backup.
    connection = sqlite3.connect(
        database_path,
        timeout=10
    )

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        validate_legacy_database(connection)
    finally:
        connection.close()

    # Migration cannot proceed without a verified backup.
    backup_path = create_verified_backup(database_path)

    print(f"Verified backup created: {backup_path}")

    connection = sqlite3.connect(
        database_path,
        timeout=10
    )

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        # Recheck the schema after backup creation.
        validate_legacy_database(connection)

        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE
                    CHECK (length(trim(email)) > 0),
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            """,
            (email, password_hash)
        )

        user_id = cursor.lastrowid

        connection.execute(
            "ALTER TABLE expenses RENAME TO expenses_legacy"
        )

        connection.execute(
            """
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL
                    CHECK (amount_cents > 0),
                category TEXT NOT NULL
                    CHECK (length(trim(category)) > 0),
                description TEXT NOT NULL DEFAULT '',
                expense_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )

        connection.execute(
            """
            INSERT INTO expenses (
                id,
                user_id,
                amount_cents,
                category,
                description,
                expense_date,
                created_at
            )
            SELECT
                id,
                ?,
                amount_cents,
                category,
                description,
                expense_date,
                created_at
            FROM expenses_legacy
            """,
            (user_id,)
        )

        connection.execute("DROP TABLE expenses_legacy")

        connection.execute(
            """
            CREATE INDEX idx_expenses_user_date
            ON expenses(user_id, expense_date)
            """
        )

        connection.execute(
            """
            CREATE INDEX idx_expenses_user_category
            ON expenses(user_id, category)
            """
        )

        connection.execute(
            f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}"
        )

        # Check database integrity before committing.
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                f"Database integrity check failed: {integrity}"
            )

        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_errors:
            raise RuntimeError(
                "Migration produced foreign-key violations."
            )

        connection.commit()

        return user_id

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate the expense database to user accounts."
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Database file to migrate."
    )

    args = parser.parse_args()

    database_path = args.database.resolve()

    if not database_path.is_file():
        print(f"Database not found: {database_path}")
        return 1

    print(f"Database: {database_path}")

    try:
        email, password_hash = get_account_details()

        user_id = migrate(
            database_path,
            email,
            password_hash
        )

        print("\nMigration completed successfully.")
        print(f"First account ID: {user_id}")
        print(f"Database schema version: {CURRENT_SCHEMA_VERSION}")

    except (ValueError, RuntimeError, sqlite3.Error, OSError) as error:
        print(f"\nMigration failed: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
