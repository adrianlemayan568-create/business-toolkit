CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    email TEXT NOT NULL UNIQUE
        CHECK (length(trim(email)) > 0),

    password_hash TEXT NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER NOT NULL,

    amount_cents INTEGER NOT NULL
        CHECK (amount_cents > 0),

    category TEXT NOT NULL
        CHECK (length(trim(category)) > 0),

    description TEXT NOT NULL DEFAULT '',

    expense_date TEXT NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
);


CREATE INDEX IF NOT EXISTS idx_expenses_user_date
ON expenses(user_id, expense_date);


CREATE INDEX IF NOT EXISTS idx_expenses_user_category
ON expenses(user_id, category);
