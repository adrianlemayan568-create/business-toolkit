import csv

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from database.db import get_connection


def add_expense(amount, category, description="", expense_date=None):
    """Save a new expense in the database."""

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid expense amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    cents = amount * 100

    if cents != cents.to_integral_value():
        raise ValueError("Amount cannot have more than two decimal places.")

    amount_cents = int(cents)

    category = category.strip()

    if not category:
        raise ValueError("Category cannot be empty.")

    if expense_date is None:
        expense_date = date.today().isoformat()
    else:
        try:
            expense_date = date.fromisoformat(expense_date).isoformat()
        except (ValueError, TypeError):
            raise ValueError("Date must use YYYY-MM-DD format.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO expenses
            (amount_cents, category, description, expense_date)
            VALUES (?, ?, ?, ?)
            """,
            (amount_cents, category, description.strip(), expense_date)
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def view_expenses():
    """Retrieve all recorded expenses."""

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT id, amount_cents, category,
                   description, expense_date
            FROM expenses
            ORDER BY expense_date DESC, id DESC
            """
        )

        return cursor.fetchall()

    finally:
        connection.close()


def get_total_expenses():
    """Calculate the total of all recorded expenses."""

    connection = get_connection()

    try:
        cursor = connection.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM expenses"
        )

        return cursor.fetchone()[0]

    finally:
        connection.close()


def get_monthly_total(year, month):
    """Calculate expenses for a specific month."""

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT COALESCE(SUM(amount_cents), 0)
            FROM expenses
            WHERE strftime('%Y', expense_date) = ?
            AND strftime('%m', expense_date) = ?
            """,
            (str(year), f"{month:02d}")
        )

        return cursor.fetchone()[0]

    finally:
        connection.close()


def get_monthly_category_totals(year, month):
    """Calculate expense totals grouped by category for a specific month."""

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT category, SUM(amount_cents) AS total_cents
            FROM expenses
            WHERE strftime('%Y', expense_date) = ?
            AND strftime('%m', expense_date) = ?
            GROUP BY category
            ORDER BY total_cents DESC
            """,
            (str(year), f"{month:02d}")
        )

        return cursor.fetchall()

    finally:
        connection.close()


def delete_expense(expense_id):
    """Delete an expense using its ID."""

    connection = get_connection()

    try:
        cursor = connection.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,)
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


def safe_csv_text(value):
    """
    Reduce CSV formula injection risks in spreadsheet applications.

    Prefix potentially dangerous text cells with an apostrophe.
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


def export_expenses():
    """Export expenses to a CSV file with formula-injection mitigation."""

    expenses = view_expenses()

    export_dir = Path(__file__).resolve().parent.parent / "exports"
    export_dir.mkdir(exist_ok=True)

    file_path = export_dir / "expenses.csv"

    with open(
        file_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

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

    return file_path


def compare_monthly_expenses(year1, month1, year2, month2):
    """Compare total expenses between two different months."""

    first_month_total = get_monthly_total(year1, month1)
    second_month_total = get_monthly_total(year2, month2)

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
    expense_id,
    amount,
    category,
    description="",
    expense_date=None
):
    """Update an existing expense using its ID."""

    if (
        isinstance(expense_id, bool)
        or not isinstance(expense_id, int)
        or expense_id <= 0
    ):
        raise ValueError("Invalid expense ID.")

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid expense amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    cents = amount * 100

    if cents != cents.to_integral_value():
        raise ValueError("Amount cannot have more than two decimal places.")

    amount_cents = int(cents)

    category = category.strip()

    if not category:
        raise ValueError("Category cannot be empty.")

    if expense_date is None:
        expense_date = date.today().isoformat()
    else:
        try:
            expense_date = date.fromisoformat(expense_date).isoformat()
        except (ValueError, TypeError):
            raise ValueError("Date must use YYYY-MM-DD format.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE expenses
            SET amount_cents = ?,
                category = ?,
                description = ?,
                expense_date = ?
            WHERE id = ?
            """,
            (
                amount_cents,
                category,
                description.strip(),
                expense_date,
                expense_id
            )
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


def get_expense(expense_id):
    """Retrieve one expense by its ID."""

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
            WHERE id = ?
            """,
            (expense_id,)
        )

        return cursor.fetchone()

    finally:
        connection.close()
