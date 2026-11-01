from database.db import initialize_database

from modules.expenses import (
    add_expense,
    view_expenses,
    get_total_expenses,
    get_monthly_total,
    get_monthly_category_totals,
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
    print("6. View monthly expense report")
    print("7. Exit")


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


def handle_monthly_report():
    try:
        year = int(input("Enter year (e.g. 2026): "))
        month = int(input("Enter month (1-12): "))

        if not 1 <= month <= 12:
            print("\nInvalid month. Enter a number between 1 and 12.")
            return

        if not 1 <= year <= 9999:
            print("\nInvalid year.")
            return

        total_cents = get_monthly_total(year, month)
        category_totals = get_monthly_category_totals(year, month)

        print("\n========================================")
        print("          MONTHLY EXPENSE REPORT")
        print("========================================")
        print(f"Month: {year}-{month:02d}")
        print(f"\nTOTAL EXPENSES: KSh {total_cents / 100:,.2f}")

        print("\nCATEGORY BREAKDOWN")
        print("----------------------------------------")

        if not category_totals:
            print("No expenses recorded for this month.")
        else:
            for item in category_totals:
                amount = item["total_cents"] / 100

                print(
                    f'{item["category"]:<20} '
                    f'KSh {amount:,.2f}'
                )

        print("----------------------------------------")
        print(f'{"TOTAL":<20} KSh {total_cents / 100:,.2f}')
        print("========================================")

    except ValueError:
        print("\nPlease enter valid numeric values.")


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

        choice = input("\nChoose an option (1-7): ").strip()

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
            handle_monthly_report()

        elif choice == "7":
            print("\nGoodbye!")
            break

        else:
            print("\nInvalid choice. Enter a number from 1 to 7.")


if __name__ == "__main__":
    main()
