from datetime import date, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash

from database.db import initialize_database
from modules.expenses import (
    add_expense,
    view_expenses,
    get_total_expenses,
    get_monthly_total,
    get_monthly_category_totals,
    compare_monthly_expenses,
    delete_expense
)

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)

# Development-only secret. Replace before deployment.
app.secret_key = "development-secret-key"

initialize_database()


@app.route("/")
def index():
    today = date.today()

    # Read the selected month from the URL.
    selected_month = request.args.get("month", today.strftime("%Y-%m"))

    try:
        selected_date = date.fromisoformat(selected_month + "-01")
    except ValueError:
        selected_date = today.replace(day=1)
        selected_month = selected_date.strftime("%Y-%m")
        flash("Invalid month selected. Showing the current month.", "error")

    year = selected_date.year
    month = selected_date.month

    # Determine the previous calendar month.
    previous_month_date = selected_date.replace(day=1) - timedelta(days=1)

    monthly_total = get_monthly_total(year, month)
    category_totals = get_monthly_category_totals(year, month)

    comparison = compare_monthly_expenses(
        previous_month_date.year,
        previous_month_date.month,
        year,
        month
    )

    expenses = view_expenses()
    total_cents = get_total_expenses()

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_cents / 100,
        today=today.isoformat(),
        selected_month=selected_month,
        monthly_total=monthly_total / 100,
        category_totals=category_totals,
        comparison=comparison,
        previous_month_label=previous_month_date.strftime("%B %Y"),
        selected_month_label=selected_date.strftime("%B %Y")
    )


@app.route("/add-expense", methods=["POST"])
def add_new_expense():
    amount = request.form.get("amount", "")
    category = request.form.get("category", "")
    description = request.form.get("description", "")
    expense_date = request.form.get("expense_date", "")

    try:
        add_expense(
            amount=amount,
            category=category,
            description=description,
            expense_date=expense_date
        )

        flash("Expense added successfully!", "success")

    except (ValueError, TypeError) as error:
        flash(str(error), "error")

    return redirect(url_for("index"))


@app.route("/delete-expense/<int:expense_id>", methods=["POST"])
def delete_expense_route(expense_id):
    deleted = delete_expense(expense_id)

    if deleted:
        flash("Expense deleted successfully.", "success")
    else:
        flash("Expense not found. Nothing was deleted.", "error")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
