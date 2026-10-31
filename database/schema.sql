CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    amount_cents INTEGER NOT NULL
        CHECK (amount_cents > 0),

    category TEXT NOT NULL
        CHECK (length(trim(category)) > 0),

    description TEXT NOT NULL DEFAULT '',

    expense_date TEXT NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expenses_date
ON expenses(expense_date);

CREATE INDEX IF NOT EXISTS idx_expenses_category
ON expenses(category);
