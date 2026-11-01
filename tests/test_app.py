
import re
import unittest
import tempfile

from pathlib import Path
from unittest.mock import patch

from app import app


class CSRFTestMixin:

    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = True
        self.client = app.test_client()

    def get_csrf_token(self, response):
        match = re.search(
            rb'name="csrf_token"\s+value="([^"]+)"',
            response.data
        )

        self.assertIsNotNone(
            match,
            "CSRF token was not found in the rendered form."
        )

        return match.group(1).decode("utf-8")

    def get_dashboard_token(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

        return self.get_csrf_token(response)


class TestExpenseRoutes(CSRFTestMixin, unittest.TestCase):

    @patch("app.delete_expense", return_value=True)
    def test_delete_existing_expense_route(self, mock_delete):
        token = self.get_dashboard_token()

        response = self.client.post(
            "/delete-expense/1",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 302)
        mock_delete.assert_called_once_with(1)

        with self.client.session_transaction() as session:
            flashes = session.get("_flashes", [])

        self.assertIn(
            ("success", "Expense deleted successfully."),
            flashes
        )

    @patch("app.delete_expense", return_value=False)
    def test_delete_nonexistent_expense_route(self, mock_delete):
        token = self.get_dashboard_token()

        response = self.client.post(
            "/delete-expense/999",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 302)
        mock_delete.assert_called_once_with(999)

        with self.client.session_transaction() as session:
            flashes = session.get("_flashes", [])

        self.assertIn(
            ("error", "Expense not found. Nothing was deleted."),
            flashes
        )

    @patch("app.delete_expense")
    def test_get_request_cannot_delete_expense(self, mock_delete):
        response = self.client.get("/delete-expense/1")

        self.assertEqual(response.status_code, 405)
        mock_delete.assert_not_called()

    @patch("app.delete_expense")
    def test_non_integer_expense_id_is_rejected(self, mock_delete):
        token = self.get_dashboard_token()

        response = self.client.post(
            "/delete-expense/abc",
            data={"csrf_token": token}
        )

        self.assertEqual(response.status_code, 404)
        mock_delete.assert_not_called()

    @patch("app.delete_expense")
    def test_delete_without_csrf_token_is_rejected(self, mock_delete):
        response = self.client.post("/delete-expense/1")

        self.assertEqual(response.status_code, 400)
        mock_delete.assert_not_called()

    @patch("app.delete_expense")
    def test_delete_with_invalid_csrf_token_is_rejected(
        self, mock_delete
    ):
        response = self.client.post(
            "/delete-expense/1",
            data={"csrf_token": "invalid-token"}
        )

        self.assertEqual(response.status_code, 400)
        mock_delete.assert_not_called()


class TestAddExpenseRoute(CSRFTestMixin, unittest.TestCase):

    @patch("app.add_expense")
    def test_successful_expense_addition(self, mock_add):
        token = self.get_dashboard_token()

        response = self.client.post(
            "/add-expense",
            data={
                "csrf_token": token,
                "amount": "250.00",
                "category": "Food",
                "description": "Lunch",
                "expense_date": "2026-11-01",
            }
        )

        self.assertEqual(response.status_code, 302)

        mock_add.assert_called_once_with(
            amount="250.00",
            category="Food",
            description="Lunch",
            expense_date="2026-11-01",
        )

    @patch("app.add_expense")
    def test_add_expense_without_csrf_token_is_rejected(
        self, mock_add
    ):
        response = self.client.post(
            "/add-expense",
            data={
                "amount": "250.00",
                "category": "Food",
                "description": "Lunch",
                "expense_date": "2026-11-01",
            }
        )

        self.assertEqual(response.status_code, 400)
        mock_add.assert_not_called()


class TestEditExpenseRoute(CSRFTestMixin, unittest.TestCase):

    def sample_expense(self):
        return {
            "id": 1,
            "amount_cents": 25000,
            "category": "Food",
            "description": "Lunch",
            "expense_date": "2026-11-01",
        }

    @patch("app.get_expense")
    def test_edit_existing_expense_loads_form(self, mock_get_expense):
        mock_get_expense.return_value = self.sample_expense()

        response = self.client.get("/edit-expense/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Edit Expense", response.data)
        self.assertIn(b"Food", response.data)
        self.assertIn(b'name="csrf_token"', response.data)

        mock_get_expense.assert_called_once_with(1)

    @patch("app.get_expense", return_value=None)
    def test_edit_nonexistent_expense_redirects(self, mock_get_expense):
        response = self.client.get("/edit-expense/999")

        self.assertEqual(response.status_code, 302)
        mock_get_expense.assert_called_once_with(999)

        with self.client.session_transaction() as session:
            flashes = session.get("_flashes", [])

        self.assertIn(("error", "Expense not found."), flashes)

    @patch("app.update_expense", return_value=True)
    @patch("app.get_expense")
    def test_successful_expense_update(
        self, mock_get_expense, mock_update
    ):
        mock_get_expense.return_value = self.sample_expense()

        form_response = self.client.get("/edit-expense/1")
        token = self.get_csrf_token(form_response)

        response = self.client.post(
            "/edit-expense/1",
            data={
                "csrf_token": token,
                "amount": "300.00",
                "category": "Transport",
                "description": "Bus fare",
                "expense_date": "2026-11-02",
            },
        )

        self.assertEqual(response.status_code, 302)

        mock_update.assert_called_once_with(
            expense_id=1,
            amount="300.00",
            category="Transport",
            description="Bus fare",
            expense_date="2026-11-02",
        )

        with self.client.session_transaction() as session:
            flashes = session.get("_flashes", [])

        self.assertIn(
            ("success", "Expense updated successfully!"),
            flashes
        )

    @patch(
        "app.update_expense",
        side_effect=ValueError("Amount must be positive.")
    )
    @patch("app.get_expense")
    def test_invalid_update_preserves_form_values(
        self, mock_get_expense, mock_update
    ):
        mock_get_expense.return_value = self.sample_expense()

        form_response = self.client.get("/edit-expense/1")
        token = self.get_csrf_token(form_response)

        response = self.client.post(
            "/edit-expense/1",
            data={
                "csrf_token": token,
                "amount": "-50",
                "category": "Transport",
                "description": "Bus fare",
                "expense_date": "2026-11-02",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"-50", response.data)
        self.assertIn(b"Transport", response.data)
        self.assertIn(b"Bus fare", response.data)

        mock_update.assert_called_once()

    @patch("app.get_expense")
    def test_edit_without_csrf_token_is_rejected(self, mock_get_expense):
        response = self.client.post(
            "/edit-expense/1",
            data={
                "amount": "300.00",
                "category": "Transport",
                "description": "Bus fare",
                "expense_date": "2026-11-02",
            }
        )

        self.assertEqual(response.status_code, 400)
        mock_get_expense.assert_not_called()


class TestMonthlyReportRoute(CSRFTestMixin, unittest.TestCase):

    def prepare_dashboard_mocks(self):
        return (
            patch("app.get_monthly_total", return_value=0),
            patch("app.get_monthly_category_totals", return_value=[]),
            patch(
                "app.compare_monthly_expenses",
                return_value={
                    "first_month_total": 0,
                    "second_month_total": 0,
                    "difference": 0,
                    "percentage_change": None
                }
            ),
            patch("app.view_expenses", return_value=[]),
            patch("app.get_total_expenses", return_value=0)
        )

    def test_selected_month_loads_correct_report(self):
        mocks = self.prepare_dashboard_mocks()

        with mocks[0] as monthly_total, \
             mocks[1] as category_totals, \
             mocks[2] as comparison, \
             mocks[3], \
             mocks[4]:

            response = self.client.get("/?month=2026-11")

        self.assertEqual(response.status_code, 200)
        monthly_total.assert_called_once_with(2026, 11)
        category_totals.assert_called_once_with(2026, 11)
        comparison.assert_called_once_with(2026, 10, 2026, 11)

    def test_january_comparison_uses_previous_december(self):
        mocks = self.prepare_dashboard_mocks()

        with mocks[0], \
             mocks[1], \
             mocks[2] as comparison, \
             mocks[3], \
             mocks[4]:

            response = self.client.get("/?month=2027-01")

        self.assertEqual(response.status_code, 200)
        comparison.assert_called_once_with(2026, 12, 2027, 1)

    def test_month_with_zero_expenses_loads_successfully(self):
        mocks = self.prepare_dashboard_mocks()

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
            response = self.client.get("/?month=2026-11")

        self.assertEqual(response.status_code, 200)

    def test_invalid_month_falls_back_safely(self):
        response = self.client.get("/?month=not-a-month")

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            b"Invalid month selected. Showing the current month.",
            response.data
        )


class TestExportRoute(CSRFTestMixin, unittest.TestCase):

    def test_csv_download_returns_correct_file(self):
        csv_content = (
            "ID,Amount (KSh),Category,Description,Date\n"
            "1,250.00,Food,Lunch,2026-11-01\n"
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "expenses.csv"
            csv_path.write_text(csv_content, encoding="utf-8")

            with patch(
                "app.export_expenses",
                return_value=csv_path
            ) as mock_export:

                response = self.client.get("/export-expenses")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")

        self.assertIn(
            "attachment",
            response.headers["Content-Disposition"]
        )

        self.assertIn(
            "expenses.csv",
            response.headers["Content-Disposition"]
        )

        self.assertEqual(response.data.decode("utf-8"), csv_content)
        response.close()

        mock_export.assert_called_once()

    def test_post_request_cannot_access_export_route(self):
        response = self.client.post("/export-expenses")

        self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
