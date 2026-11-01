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


if __name__ == "__main__":
    unittest.main()
