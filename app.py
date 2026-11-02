
import os
import secrets
from datetime import date, timedelta
from functools import wraps

from flask import (
    Flask,
    Response,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    g
)

from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from database.db import verify_database_schema

from modules.users import (
    authenticate_user,
    get_user_by_id
)

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


# --------------------------------------------------
# APPLICATION CONFIGURATION
# --------------------------------------------------

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)


APP_ENV = os.environ.get(
    "APP_ENV",
    "development"
).strip().lower()

if APP_ENV not in {"development", "production"}:
    raise RuntimeError(
        "APP_ENV must be either development or production."
    )


# --------------------------------------------------
# SECRET KEY
# --------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")

if APP_ENV == "production" and not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY must be configured in production."
    )

app.config["SECRET_KEY"] = (
    SECRET_KEY or secrets.token_hex(32)
)


# --------------------------------------------------
# SESSION SECURITY
# --------------------------------------------------

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = (
    APP_ENV == "production"
)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)


# --------------------------------------------------
# RATE LIMITING
# --------------------------------------------------

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=True
)


# --------------------------------------------------
# CSRF PROTECTION
# --------------------------------------------------

csrf = CSRFProtect(app)


# --------------------------------------------------
# DATABASE VERIFICATION
# --------------------------------------------------

@app.before_request
def verify_database_before_request():
    """
    Verify the database before the application serves requests.

    Verification is cached after the first successful check.
    """

    if not app.extensions.get("database_verified", False):
        verify_database_schema()

        app.extensions["database_verified"] = True


# --------------------------------------------------
# LOAD CURRENT USER
# --------------------------------------------------

@app.before_request
def load_current_user():
    """
    Load the authenticated account from the session.

    Invalid or deleted accounts lose their session.
    """

    user_id = session.get("user_id")

    if user_id is None:
        g.current_user = None
        return

    user = get_user_by_id(user_id)

    if user is None:
        session.clear()
        g.current_user = None
        return

    g.current_user = user


# --------------------------------------------------
# AUTHENTICATION DECORATOR
# --------------------------------------------------

def login_required(view):
    """
    Require an authenticated account before accessing a route.
    """

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if g.current_user is None:
            flash(
                "Please log in to continue.",
                "error"
            )

            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():

    # Already authenticated users go to the dashboard.
    if g.current_user is not None:
        return redirect(url_for("index"))

    if request.method == "POST":

        email = request.form.get("email", "")
        password = request.form.get("password", "")

        user = authenticate_user(email, password)

        if user is None:
            flash(
                "Invalid email address or password.",
                "error"
            )

            return render_template("login.html"), 401

        # Prevent session fixation.
        session.clear()

        session["user_id"] = user["id"]
        session.permanent = True

        flash(
            "Welcome back!",
            "success"
        )

        return redirect(url_for("index"))

    return render_template("login.html")


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout", methods=["POST"])
@login_required
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(url_for("login"))


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/")
@login_required
def index():

    user_id = g.current_user["id"]

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

    monthly_total = get_monthly_total(
        user_id,
        year,
        month
    )

    category_totals = get_monthly_category_totals(
        user_id,
        year,
        month
    )

    comparison = compare_monthly_expenses(
        user_id,
        previous_month_date.year,
        previous_month_date.month,
        year,
        month
    )

    expenses = view_expenses(user_id)

    total_cents = get_total_expenses(user_id)

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
@login_required
def add_new_expense():

    user_id = g.current_user["id"]

    amount = request.form.get("amount", "")
    category = request.form.get("category", "")
    description = request.form.get("description", "")
    expense_date = request.form.get("expense_date", "")

    try:

        add_expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            expense_date=expense_date
        )

        flash(
            "Expense added successfully!",
            "success"
        )

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
@login_required
def edit_expense_route(expense_id):

    user_id = g.current_user["id"]

    # Ownership is checked by the database query.
    expense = get_expense(
        user_id,
        expense_id
    )

    if expense is None:

        flash(
            "Expense not found.",
            "error"
        )

        return redirect(url_for("index"))

    form_values = None

    if request.method == "POST":

        amount = request.form.get("amount", "")
        category = request.form.get("category", "")
        description = request.form.get("description", "")
        expense_date = request.form.get("expense_date", "")

        try:

            updated = update_expense(
                user_id=user_id,
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
@login_required
def delete_expense_route(expense_id):

    user_id = g.current_user["id"]

    deleted = delete_expense(
        user_id,
        expense_id
    )

    if deleted:

        flash(
            "Expense deleted successfully.",
            "success"
        )

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
@login_required
def export_expenses_route():

    user_id = g.current_user["id"]

    csv_content = export_expenses(user_id)

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                'attachment; filename="expenses.csv"'
        }
    )


# --------------------------------------------------
# APPLICATION ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":

    debug_mode = (
        APP_ENV != "production"
        and os.environ.get("FLASK_DEBUG") == "1"
    )

    app.run(
        debug=debug_mode
    )
