import re

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database.db import get_connection


def normalize_email(email):
    """Normalize and validate an email address."""

    if not isinstance(email, str):
        raise ValueError("A valid email address is required.")

    email = email.strip().lower()

    if len(email) > 254:
        raise ValueError("Email address is too long.")

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    if not re.fullmatch(pattern, email):
        raise ValueError("Enter a valid email address.")

    return email


def create_user(email, password):
    """Create a user account with a securely hashed password."""

    email = normalize_email(email)

    if not isinstance(password, str):
        raise ValueError("Password must be text.")

    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")

    if len(password) > 128:
        raise ValueError("Password is too long.")

    password_hash = generate_password_hash(password)

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            """,
            (email, password_hash)
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def get_user_by_email(email):
    """Retrieve an account using its normalized email address."""

    email = normalize_email(email)

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT id, email, password_hash, created_at
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

    finally:
        connection.close()


def get_user_by_id(user_id):
    """Retrieve an account using its ID."""

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        return None

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT id, email, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

    finally:
        connection.close()


def authenticate_user(email, password):
    """Verify login credentials."""

    if not isinstance(password, str):
        return None

    try:
        user = get_user_by_email(email)
    except ValueError:
        return None

    if user is None:
        return None

    if not check_password_hash(
        user["password_hash"],
        password
    ):
        return None

    return user
