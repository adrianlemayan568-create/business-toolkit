
import os
import sqlite3
from pathlib import Path


# --------------------------------------------------
# PROJECT PATHS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

_configured_database_path = os.environ.get("DATABASE_PATH")

if _configured_database_path:
    DATABASE_PATH = Path(_configured_database_path).expanduser()

    if not DATABASE_PATH.is_absolute():
        raise RuntimeError(
            "DATABASE_PATH must be an absolute path."
        )
else:
    DATABASE_PATH = BASE_DIR / "database" / "business.db"

SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

EXPECTED_SCHEMA_VERSION = 1


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_connection():
    """
    Create a SQLite database connection.

    Foreign-key enforcement is enabled for every connection.
    """

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# --------------------------------------------------
# DATABASE VERIFICATION
# --------------------------------------------------

def verify_database_schema():
    """
    Verify that the migrated database exists and has
    the expected schema version and required tables.

    This function does not create or modify the database.
    """

    if not DATABASE_PATH.is_file():
        raise RuntimeError(
            f"Database file not found: {DATABASE_PATH}"
        )

    connection = get_connection()

    try:
        # Check schema version.
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version != EXPECTED_SCHEMA_VERSION:
            raise RuntimeError(
                f"Unsupported database schema version: {version}. "
                f"Expected version {EXPECTED_SCHEMA_VERSION}. "
                "Run the database migration first."
            )

        # Check required tables.
        required_tables = {
            "users",
            "expenses"
        }

        existing_tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        missing_tables = required_tables - existing_tables

        if missing_tables:
            raise RuntimeError(
                "Required database tables are missing: "
                + ", ".join(sorted(missing_tables))
            )

        # Check required expense ownership column.
        expense_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(expenses)"
            ).fetchall()
        }

        if "user_id" not in expense_columns:
            raise RuntimeError(
                "The expenses table is missing the user_id column."
            )

        # Check required user account columns.
        user_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }

        required_user_columns = {
            "id",
            "email",
            "password_hash"
        }

        missing_user_columns = (
            required_user_columns - user_columns
        )

        if missing_user_columns:
            raise RuntimeError(
                "The users table is missing required columns: "
                + ", ".join(sorted(missing_user_columns))
            )

        return True

    finally:
        connection.close()


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------
def initialize_database():
    """
    Initialize a fresh database using the current schema.

    Refuses to overwrite an existing database containing
    application tables or a non-zero schema version.
    """

    if DATABASE_PATH.exists():
        connection = sqlite3.connect(DATABASE_PATH)

        try:
            existing_tables = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            if existing_tables or version != 0:
                raise RuntimeError(
                    "Database already contains data or has "
                    "a schema version. Initialization refused."
                )

        finally:
            connection.close()

    connection = get_connection()

    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")

        connection.executescript(
            "BEGIN IMMEDIATE;\n"
            + schema
            + f"\nPRAGMA user_version = {EXPECTED_SCHEMA_VERSION};\n"
            + "COMMIT;"
        )

    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise

    finally:
        connection.close()

# DIRECT EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    initialize_database()

    print("Database initialized successfully!")
    print(f"Database location: {DATABASE_PATH}")
