
import re
import unittest
from unittest.mock import patch

from app import app


TEST_USER_ID = 7
TEST_EMAIL = "test@example.com"

TEST_USER = {
    "id": TEST_USER_ID,
    "email": TEST_EMAIL
}

TEST_COMPARISON = {
    "first_month_total": 0,
    "second_month_total": 0,
    "difference": 0,
    "percentage_change": None
}


class FlaskAppTestCase(unittest.TestCase):

    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=True,
            SECRET_KEY="test-secret-key"
        )

        app.extensions.pop("database_verified", None)

        self.client = app.test_client()

        self.database_patch = patch(
            "app.verify_database_schema"
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

        self.user_patch = patch(
            "app.get_user_by_id",
            return_value=TEST_USER
        )
        self.user_patch.start()
        self.addCleanup(self.user_patch.stop)

        self.dashboard_patches = [
            patch("app.get_monthly_total", return_value=0),
            patch("app.get_monthly_category_totals", return_value=[]),
            patch(
                "app.compare_monthly_expenses",
                return_value=TEST_COMPARISON
            ),
            patch("app.view_expenses", return_value=[]),
            patch("app.get_total_expenses", return_value=0)
        ]

        self.dashboard_mocks = []

        for patcher in self.dashboard_patches:
            self.dashboard_mocks.append(patcher.start())
            self.addCleanup(patcher.stop)

        with self.client.session_transaction() as session:
            session["user_id"] = TEST_USER_ID

    def get_csrf_token(self, client=None, url="/"):
        if client is None:
            client = self.client

        response = client.get(url)

        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)

        match = re.search(
            r'name="csrf_token"\s+type="hidden"\s+value="([^"]+)"',
            html
        )

        if match is None:
            match = re.search(
                r'name="csrf_token"\s+value="([^"]+)"',
                html
            )

        self.assertIsNotNone(
            match,
            "CSRF token was not found in the page."
        )

        return match.group(1)

    def get_login_csrf_token(self, client=None):
        return self.get_csrf_token(
            client=client,
            url="/login"
        )


# --------------------------------------------------
# AUTHENTICATION TESTS
# --------------------------------------------------

class TestAuthentication(FlaskAppTestCase):

    def test_login_page_loads(self):
        client = app.test_client()

        response = client.get("/login")

        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)

        self.assertIn('name="email"', html)
        self.assertIn('name="password"', html)
        self.assertIn("csrf_token", html)

    @patch("app.authenticate_user")
    def test_successful_login(self, mock_authenticate):
        mock_authenticate.return_value = TEST_USER

        client = app.test_client()

        token = self.get_login_csrf_token(client)

        response = client.post(
            "/login",
            data={
                "email": TEST_EMAIL,
                "password": "correct-password",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")

        mock_authenticate.assert_called_once_with(
            TEST_EMAIL,
            "correct-password"
        )

        with client.session_transaction() as session:
            self.assertEqual(
                session.get("user_id"),
                TEST_USER_ID
            )

    @patch("app.authenticate_user")
    def test_failed_login(self, mock_authenticate):
        mock_authenticate.return_value = None

        client = app.test_client()

        token = self.get_login_csrf_token(client)

        response = client.post(
            "/login",
            data={
                "email": TEST_EMAIL,
                "password": "wrong-password",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 401)

        self.assertIn(
            "Invalid email address or password.",
            response.get_data(as_text=True)
        )

        with client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    @patch("app.authenticate_user")
    def test_login_rejects_missing_csrf_token(self, mock_authenticate):
        client = app.test_client()

        response = client.post(
            "/login",
            data={
                "email": TEST_EMAIL,
                "password": "correct-password"
            }
        )

        self.assertEqual(response.status_code, 400)
        mock_authenticate.assert_not_called()

    def test_logged_in_user_cannot_access_login_page(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")

    def test_logout_clears_session(self):
        token = self.get_csrf_token()

        response = self.client.post(
            "/logout",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_logout_requires_post(self):
        response = self.client.get("/logout")

        self.assertEqual(response.status_code, 405)

    def test_logout_requires_csrf_token(self):
        response = self.client.post("/logout")

        self.assertEqual(response.status_code, 400)

    def test_deleted_account_loses_session(self):
        with patch(
            "app.get_user_by_id",
            return_value=None
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)


# --------------------------------------------------
# ROUTE PROTECTION TESTS
# --------------------------------------------------

class TestRouteProtection(FlaskAppTestCase):

    def setUp(self):
        super().setUp()
        self.unauthenticated_client = app.test_client()

    def test_dashboard_requires_login(self):
        response = self.unauthenticated_client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

    def test_export_requires_login(self):
        response = self.unauthenticated_client.get(
            "/export-expenses"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

    def test_add_expense_requires_login(self):
        token = self.get_login_csrf_token(
            self.unauthenticated_client
        )

        response = self.unauthenticated_client.post(
            "/add-expense",
            data={
                "amount": "100",
                "category": "Food",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

    def test_edit_expense_requires_login(self):
        response = self.unauthenticated_client.get(
            "/edit-expense/1"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

    def test_delete_expense_requires_login(self):
        token = self.get_login_csrf_token(
            self.unauthenticated_client
        )

        response = self.unauthenticated_client.post(
            "/delete-expense/1",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")


# --------------------------------------------------
# DASHBOARD TESTS
# --------------------------------------------------

class TestDashboard(FlaskAppTestCase):

    def test_dashboard_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_dashboard_uses_authenticated_user_id(self):
        self.client.get("/")

        self.dashboard_mocks[0].assert_called_once()
        self.dashboard_mocks[0].assert_called_with(
            TEST_USER_ID,
            unittest.mock.ANY,
            unittest.mock.ANY
        )

        self.dashboard_mocks[1].assert_called_once()
        self.dashboard_mocks[1].assert_called_with(
            TEST_USER_ID,
            unittest.mock.ANY,
            unittest.mock.ANY
        )

        self.dashboard_mocks[3].assert_called_once_with(
            TEST_USER_ID
        )

        self.dashboard_mocks[4].assert_called_once_with(
            TEST_USER_ID
        )

    def test_dashboard_handles_invalid_month(self):
        response = self.client.get("/?month=invalid")

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            "Invalid month selected.",
            response.get_data(as_text=True)
        )


# --------------------------------------------------
# ADD EXPENSE TESTS
# --------------------------------------------------

class TestAddExpense(FlaskAppTestCase):

    @patch("app.add_expense")
    def test_add_expense_success(self, mock_add):
        token = self.get_csrf_token()

        response = self.client.post(
            "/add-expense",
            data={
                "amount": "100",
                "category": "Food",
                "description": "Lunch",
                "expense_date": "2026-11-01",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 302)
        mock_add.assert_called_once()

        kwargs = mock_add.call_args.kwargs

        self.assertEqual(kwargs["user_id"], TEST_USER_ID)
        self.assertEqual(kwargs["amount"], "100")
        self.assertEqual(kwargs["category"], "Food")

    @patch("app.add_expense")
    def test_add_expense_handles_invalid_data(self, mock_add):
        mock_add.side_effect = ValueError("Invalid expense amount.")

        token = self.get_csrf_token()

        response = self.client.post(
            "/add-expense",
            data={
                "amount": "-100",
                "category": "Food",
                "expense_date": "2026-11-01",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 302)

    def test_add_expense_rejects_missing_csrf(self):
        response = self.client.post(
            "/add-expense",
            data={
                "amount": "100",
                "category": "Food"
            }
        )

        self.assertEqual(response.status_code, 400)


# --------------------------------------------------
# EDIT EXPENSE TESTS
# --------------------------------------------------

class TestEditExpense(FlaskAppTestCase):

    @patch("app.get_expense")
    def test_edit_page_loads(self, mock_get):
        mock_get.return_value = {
            "id": 1,
            "amount_cents": 10000,
            "category": "Food",
            "description": "Lunch",
            "expense_date": "2026-11-01"
        }

        response = self.client.get("/edit-expense/1")

        self.assertEqual(response.status_code, 200)
        mock_get.assert_called_once_with(TEST_USER_ID, 1)

    @patch("app.get_expense")
    def test_edit_nonexistent_expense(self, mock_get):
        mock_get.return_value = None

        response = self.client.get("/edit-expense/999")

        self.assertEqual(response.status_code, 302)
        mock_get.assert_called_once_with(TEST_USER_ID, 999)

    @patch("app.update_expense")
    @patch("app.get_expense")
    def test_update_expense_success(self, mock_get, mock_update):
        mock_get.return_value = {
            "id": 1,
            "amount_cents": 10000,
            "category": "Food",
            "description": "Lunch",
            "expense_date": "2026-11-01"
        }

        mock_update.return_value = True

        token = self.get_csrf_token(
            url="/edit-expense/1"
        )

        response = self.client.post(
            "/edit-expense/1",
            data={
                "amount": "250",
                "category": "Transport",
                "description": "Bus fare",
                "expense_date": "2026-11-02",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 302)

        kwargs = mock_update.call_args.kwargs

        self.assertEqual(kwargs["user_id"], TEST_USER_ID)
        self.assertEqual(kwargs["expense_id"], 1)
        self.assertEqual(kwargs["amount"], "250")
        self.assertEqual(kwargs["category"], "Transport")

    @patch("app.update_expense")
    @patch("app.get_expense")
    def test_update_handles_invalid_data(self, mock_get, mock_update):
        mock_get.return_value = {
            "id": 1,
            "amount_cents": 10000,
            "category": "Food",
            "description": "Lunch",
            "expense_date": "2026-11-01"
        }

        mock_update.side_effect = ValueError(
            "Amount must be greater than zero."
        )

        token = self.get_csrf_token(
            url="/edit-expense/1"
        )

        response = self.client.post(
            "/edit-expense/1",
            data={
                "amount": "-50",
                "category": "Food",
                "description": "Lunch",
                "expense_date": "2026-11-01",
                "csrf_token": token
            }
        )

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            "Amount must be greater than zero.",
            response.get_data(as_text=True)
        )


# --------------------------------------------------
# DELETE EXPENSE TESTS
# --------------------------------------------------

class TestDeleteExpense(FlaskAppTestCase):

    @patch("app.delete_expense")
    def test_delete_expense_success(self, mock_delete):
        mock_delete.return_value = True

        token = self.get_csrf_token()

        response = self.client.post(
            "/delete-expense/1",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 302)

        mock_delete.assert_called_once_with(
            TEST_USER_ID,
            1
        )

    @patch("app.delete_expense")
    def test_delete_nonexistent_expense(self, mock_delete):
        mock_delete.return_value = False

        token = self.get_csrf_token()

        response = self.client.post(
            "/delete-expense/999",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 302)

        mock_delete.assert_called_once_with(
            TEST_USER_ID,
            999
        )

    def test_delete_requires_post(self):
        response = self.client.get("/delete-expense/1")

        self.assertEqual(response.status_code, 405)

    def test_delete_rejects_missing_csrf(self):
        response = self.client.post("/delete-expense/1")

        self.assertEqual(response.status_code, 400)


# --------------------------------------------------
# CSV EXPORT TESTS
# --------------------------------------------------

class TestExportExpenses(FlaskAppTestCase):

    @patch("app.export_expenses")
    def test_export_expenses(self, mock_export):
        csv_content = (
            "ID,Amount (KSh),Category,Description,Date\n"
            "1,100.00,Food,Lunch,2026-11-01\n"
        )

        mock_export.return_value = csv_content

        response = self.client.get("/export-expenses")

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.mimetype,
            "text/csv"
        )

        self.assertIn(
            'attachment; filename="expenses.csv"',
            response.headers["Content-Disposition"]
        )

        self.assertEqual(
            response.get_data(as_text=True),
            csv_content
        )

        mock_export.assert_called_once_with(TEST_USER_ID)


if __name__ == "__main__":
    unittest.main()
