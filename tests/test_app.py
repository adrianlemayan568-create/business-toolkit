import unittest
from unittest.mock import patch

from app import app


class TestExpenseRoutes(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    @patch("app.delete_expense", return_value=True)
    def test_delete_existing_expense_route(self, mock_delete):
        response = self.client.post("/delete-expense/1")

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
        response = self.client.post("/delete-expense/999")

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
        response = self.client.post("/delete-expense/abc")

        self.assertEqual(response.status_code, 404)
        mock_delete.assert_not_called()


class TestMonthlyReportRoute(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

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


if __name__ == "__main__":
    unittest.main()
