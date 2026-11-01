from datetime import date

from flask import Flask, render_template, request, redirect, url_for, flash

from database.db import initialize_database
from modules.expenses import (
    add_expense,
    view_expenses,
    get_total_expenses
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
    expenses = view_expenses()
    total_cents = get_total_expenses()

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_cents / 100,
        today=date.today().isoformat()
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


if __name__ == "__main__":
    app.run(debug=True)
