
"""
Legacy command-line entry point.

The application now uses Flask with individual user accounts.
The old unauthenticated CLI has been disabled.
"""


def main():
    print("\nBUSINESS TOOLKIT")
    print("----------------")
    print("The legacy command-line interface is disabled.")
    print("Please use the authenticated Flask application instead.")
    print("\nNo database was opened or modified.")


if __name__ == "__main__":
    main()
