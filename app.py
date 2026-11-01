
import os
import secrets
from datetime import date, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)

from flask_wtf.csrf import CSRFProtect

from database.db import initialize_database

from modules.expenses import (
    add_expense,
    view_expenses,
    get_expense,
    get_total_expenses,
    get_monthly_total,
    get_monthly_category_totals,
    compare_monthly_expenses,
    delete_expense,
    update_expense,
    export_expenses
)


app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)


# --------------------------------------------------
# APPLICATION ENVIRONMENT
# --------------------------------------------------

APP_ENV = os.environ.get(
    "APP_ENV",
    "development"
).strip().lower()

if APP_ENV not in {"development", "production"}:
    raise RuntimeError(
        "APP_ENV must be either development or production."
    )


# --------------------------------------------------
# SECRET KEY CONFIGURATION
# --------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")

# Production must always use a persistent secret key.
if APP_ENV == "production" and not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY must be configured in production."
    )

# A temporary random key is acceptable for local development.
app.config["SECRET_KEY"] = (
    SECRET_KEY or secrets.token_hex(32)
)


# --------------------------------------------------
# SESSION COOKIE SECURITY
# --------------------------------------------------

# JavaScript cannot access the session cookie.
app.config["SESSION_COOKIE_HTTPONLY"] = True

# Reduces cross-site cookie sending.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Production cookies must only travel over HTTPS.
app.config["SESSION_COOKIE_SECURE"] = (
    APP_ENV == "production"
)


# --------------------------------------------------
# CSRF PROTECTION
# --------------------------------------------------

csrf = CSRFProtect(app)


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

initialize_database()


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/")
def index():
    today = date.today()

    selected_month = request.args.get(
        "month",
        today.strftime("%Y-%m")
    )

    try:
        selected_date = date.fromisoformat(
            selected_month + "-01"
        )
    except ValueError:
        selected_date = today.replace(day=1)
        selected_month = selected_date.strftime("%Y-%m")

        flash(
            "Invalid month selected. Showing the current month.",
            "error"
        )

    year = selected_date.year
    month = selected_date.month

    previous_month_date = (
        selected_date.replace(day=1) - timedelta(days=1)
    )

    monthly_total = get_monthly_total(year, month)

    category_totals = get_monthly_category_totals(
        year,
        month
    )

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
        previous_month_label=previous_month_date.strftime(
            "%B %Y"
        ),
        selected_month_label=selected_date.strftime(
            "%B %Y"
        )
    )


# --------------------------------------------------
# ADD EXPENSE
# --------------------------------------------------

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


# --------------------------------------------------
# EDIT EXPENSE
# --------------------------------------------------

@app.route(
    "/edit-expense/<int:expense_id>",
    methods=["GET", "POST"]
)
def edit_expense_route(expense_id):

    expense = get_expense(expense_id)

    if expense is None:
        flash("Expense not found.", "error")
        return redirect(url_for("index"))

    form_values = None

    if request.method == "POST":
        amount = request.form.get("amount", "")
        category = request.form.get("category", "")
        description = request.form.get("description", "")
        expense_date = request.form.get("expense_date", "")

        try:
            updated = update_expense(
                expense_id=expense_id,
                amount=amount,
                category=category,
                description=description,
                expense_date=expense_date
            )

            if updated:
                flash(
                    "Expense updated successfully!",
                    "success"
                )
            else:
                flash(
                    "Expense not found. Nothing was updated.",
                    "error"
                )

            return redirect(url_for("index"))

        except (ValueError, TypeError) as error:
            flash(str(error), "error")

            # Preserve submitted values if validation fails.
            form_values = {
                "amount": amount,
                "category": category,
                "description": description,
                "expense_date": expense_date
            }

    return render_template(
        "edit_expense.html",
        expense=expense,
        form_values=form_values
    )


# --------------------------------------------------
# DELETE EXPENSE
# --------------------------------------------------

@app.route(
    "/delete-expense/<int:expense_id>",
    methods=["POST"]
)
def delete_expense_route(expense_id):
    deleted = delete_expense(expense_id)

    if deleted:
        flash("Expense deleted successfully.", "success")
    else:
        flash(
            "Expense not found. Nothing was deleted.",
            "error"
        )

    return redirect(url_for("index"))


# --------------------------------------------------
# EXPORT EXPENSES
# --------------------------------------------------

@app.route("/export-expenses")
def export_expenses_route():
    csv_file = export_expenses()

    return send_file(
        csv_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name="expenses.csv"
    )


# --------------------------------------------------
# APPLICATION ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":
    debug_mode = (
        APP_ENV != "production"
        and os.environ.get("FLASK_DEBUG") == "1"
    )

    app.run(debug=debug_mode)
