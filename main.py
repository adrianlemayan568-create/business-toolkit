from database.db import initialize_database
from modules.expenses import (
    add_expense,
    view_expenses,
    get_total_expenses,
    delete_expense,
    export_expenses
)


def display_menu():
    print("\n===== BUSINESS EXPENSE TRACKER =====")
    print("1. Add expense")
    print("2. View all expenses")
    print("3. View total expenses")
    print("4. Delete an expense")
    print("5. Export expenses to CSV")
    print("6. Exit")


def handle_add_expense():
    try:
        amount = input("Amount (KSh): ")
        category = input("Category: ")
        description = input("Description: ")

        expense_id = add_expense(amount, category, description)
        print(f"\nExpense saved successfully. ID: {expense_id}")

    except ValueError as error:
        print(f"\nError: {error}")


def handle_view_expenses():
    expenses = view_expenses()

    if not expenses:
        print("\nNo expenses recorded yet.")
        return

    print("\n===== RECORDED EXPENSES =====")

    for expense in expenses:
        amount = expense["amount_cents"] / 100

        print(
            f'ID: {expense["id"]} | '
            f'KSh {amount:.2f} | '
            f'{expense["category"]} | '
            f'{expense["description"]} | '
            f'{expense["expense_date"]}'
        )


def handle_total_expenses():
    total = get_total_expenses() / 100
    print(f"\nTotal expenses: KSh {total:.2f}")


def handle_delete_expense():
    expenses = view_expenses()

    if not expenses:
        print("\nThere are no expenses to delete.")
        return

    handle_view_expenses()

    try:
        expense_id = int(input("\nEnter expense ID to delete: "))

        confirm = input(
            f"Are you sure you want to delete expense "
            f"{expense_id}? (yes/no): "
        ).strip().lower()

        if confirm != "yes":
            print("\nDeletion cancelled.")
            return

        if delete_expense(expense_id):
            print("\nExpense deleted successfully.")
        else:
            print("\nExpense ID not found.")

    except ValueError:
        print("\nPlease enter a valid numeric ID.")


def handle_export_expenses():
    try:
        file_path = export_expenses()
        print("\nExpenses exported successfully!")
        print(f"File location: {file_path}")

    except OSError as error:
        print(f"\nExport failed: {error}")


def main():
    initialize_database()

    while True:
        display_menu()

        choice = input("\nChoose an option (1-6): ").strip()

        if choice == "1":
            handle_add_expense()

        elif choice == "2":
            handle_view_expenses()

        elif choice == "3":
            handle_total_expenses()

        elif choice == "4":
            handle_delete_expense()

        elif choice == "5":
            handle_export_expenses()

        elif choice == "6":
            print("\nGoodbye!")
            break

        else:
            print("\nInvalid choice. Enter a number from 1 to 6.")


if __name__ == "__main__":
    main()
