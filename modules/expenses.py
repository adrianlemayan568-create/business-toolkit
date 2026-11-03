
import csv
import io

from datetime import date
from decimal import Decimal, InvalidOperation

from database.db import get_connection


def validate_user_id(user_id):
    """Validate an account ID before database operations."""

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        raise ValueError("Invalid user ID.")


MAX_EXPENSE_AMOUNT = Decimal("999999999.99")
MAX_CATEGORY_LENGTH = 50
MAX_DESCRIPTION_LENGTH = 500


def validate_expense_fields(amount, category, description="", expense_date=None):
    """Validate and normalize all user-supplied expense fields."""

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid expense amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if amount > MAX_EXPENSE_AMOUNT:
        raise ValueError("Amount cannot exceed KSh 999,999,999.99.")

    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError("Amount cannot have more than two decimal places.")

    amount_cents = int(cents)

    if not isinstance(category, str):
        raise ValueError("Category must be text.")
    category = category.strip()
    if not category:
        raise ValueError("Category cannot be empty.")
    if len(category) > MAX_CATEGORY_LENGTH:
        raise ValueError("Category cannot exceed 50 characters.")

    if not isinstance(description, str):
        raise ValueError("Description must be text.")
    description = description.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError("Description cannot exceed 500 characters.")

    if expense_date is None:
        expense_date = date.today().isoformat()
    else:
        if not isinstance(expense_date, str):
            raise ValueError("Date must use YYYY-MM-DD format.")
        try:
            expense_date = date.fromisoformat(expense_date).isoformat()
        except (ValueError, TypeError):
            raise ValueError("Date must use YYYY-MM-DD format.")

    return amount_cents, category, description, expense_date


def add_expense(
    user_id,
    amount,
    category,
    description="",
    expense_date=None
):
    """Save a new expense belonging to a specific user."""

    validate_user_id(user_id)

    amount_cents, category, description, expense_date = (
        validate_expense_fields(amount, category, description, expense_date)
    )

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                user_id,
                amount_cents,
                category,
                description,
                expense_date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                amount_cents,
                category,
                description,
                expense_date
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def view_expenses(user_id):
    """Retrieve only the expenses belonging to one user."""

    validate_user_id(user_id)

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT id, amount_cents, category,
                   description, expense_date
            FROM expenses
            WHERE user_id = ?
            ORDER BY expense_date DESC, id DESC
            """,
            (user_id,)
        )

        return cursor.fetchall()

    finally:
        connection.close()


def get_total_expenses(user_id):
    """Calculate the total expenses belonging to one user."""

    validate_user_id(user_id)

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT COALESCE(SUM(amount_cents), 0)
            FROM expenses
            WHERE user_id = ?
            """,
            (user_id,)
        )

        return cursor.fetchone()[0]

    finally:
        connection.close()


def get_monthly_total(user_id, year, month):
    """Calculate one user's expenses for a specific month."""

    validate_user_id(user_id)

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT COALESCE(SUM(amount_cents), 0)
            FROM expenses
            WHERE user_id = ?
            AND strftime('%Y', expense_date) = ?
            AND strftime('%m', expense_date) = ?
            """,
            (user_id, str(year), f"{month:02d}")
        )

        return cursor.fetchone()[0]

    finally:
        connection.close()


def get_monthly_category_totals(user_id, year, month):
    """Calculate one user's monthly totals grouped by category."""

    validate_user_id(user_id)

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT category, SUM(amount_cents) AS total_cents
            FROM expenses
            WHERE user_id = ?
            AND strftime('%Y', expense_date) = ?
            AND strftime('%m', expense_date) = ?
            GROUP BY category
            ORDER BY total_cents DESC
            """,
            (user_id, str(year), f"{month:02d}")
        )

        return cursor.fetchall()

    finally:
        connection.close()


def delete_expense(user_id, expense_id):
    """Delete an expense only if it belongs to the specified user."""

    validate_user_id(user_id)

    if (
        isinstance(expense_id, bool)
        or not isinstance(expense_id, int)
        or expense_id <= 0
    ):
        raise ValueError("Invalid expense ID.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            DELETE FROM expenses
            WHERE id = ? AND user_id = ?
            """,
            (expense_id, user_id)
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


def safe_csv_text(value):
    """
    Reduce CSV formula injection risks in spreadsheet applications.
    """

    if not isinstance(value, str):
        return value

    stripped_value = value.lstrip(" \t\r\n")

    dangerous_prefixes = ("=", "+", "-", "@")

    if (
        value.startswith(("\t", "\r", "\n"))
        or stripped_value.startswith(dangerous_prefixes)
    ):
        return "'" + value

    return value


def export_expenses(user_id):
    """Return a CSV containing only one user's expenses."""

    expenses = view_expenses(user_id)

    output = io.StringIO(newline="")

    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Amount (KSh)",
        "Category",
        "Description",
        "Date"
    ])

    for expense in expenses:
        writer.writerow([
            expense["id"],
            f'{expense["amount_cents"] / 100:.2f}',
            safe_csv_text(expense["category"]),
            safe_csv_text(expense["description"]),
            expense["expense_date"]
        ])

    return output.getvalue()


def compare_monthly_expenses(
    user_id,
    year1,
    month1,
    year2,
    month2
):
    """Compare two months for one user's expenses."""

    validate_user_id(user_id)

    first_month_total = get_monthly_total(
        user_id, year1, month1
    )

    second_month_total = get_monthly_total(
        user_id, year2, month2
    )

    difference = second_month_total - first_month_total

    if first_month_total == 0:
        percentage_change = None
    else:
        percentage_change = (
            difference / first_month_total
        ) * 100

    return {
        "first_month_total": first_month_total,
        "second_month_total": second_month_total,
        "difference": difference,
        "percentage_change": percentage_change
    }


def update_expense(
    user_id,
    expense_id,
    amount,
    category,
    description="",
    expense_date=None
):
    """Update an expense only if it belongs to the specified user."""

    validate_user_id(user_id)

    if (
        isinstance(expense_id, bool)
        or not isinstance(expense_id, int)
        or expense_id <= 0
    ):
        raise ValueError("Invalid expense ID.")

    amount_cents, category, description, expense_date = (
        validate_expense_fields(amount, category, description, expense_date)
    )

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE expenses
            SET amount_cents = ?,
                category = ?,
                description = ?,
                expense_date = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                amount_cents,
                category,
                description,
                expense_date,
                expense_id,
                user_id
            )
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


def get_expense(user_id, expense_id):
    """Retrieve one expense only if it belongs to the specified user."""

    validate_user_id(user_id)

    if (
        isinstance(expense_id, bool)
        or not isinstance(expense_id, int)
        or expense_id <= 0
    ):
        raise ValueError("Invalid expense ID.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT id, amount_cents, category,
                   description, expense_date
            FROM expenses
            WHERE id = ? AND user_id = ?
            """,
            (expense_id, user_id)
        )

        return cursor.fetchone()

    finally:
        connection.close()
