import sqlite3
from pathlib import Path


# Locate the project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database location
DATABASE_PATH = BASE_DIR / "database" / "business.db"

# SQL schema location
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


def get_connection():
    """Create a connection to the SQLite database."""

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    """Create database tables if they don't exist."""

    connection = get_connection()

    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")

        connection.executescript(schema)

        connection.commit()

    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully!")
    print(f"Database location: {DATABASE_PATH}")
