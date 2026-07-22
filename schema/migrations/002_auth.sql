-- 002: API-layer authentication (FRONTEND_IMPLEMENTATION_PLAN.md OQ-1,
-- approved). Additive only: new table, no existing table or column touched.
-- src/ never reads this table — it exists solely for api/ login.

CREATE TABLE auth_credentials (
    user_id        INTEGER PRIMARY KEY REFERENCES users(user_id),
    password_hash  TEXT NOT NULL,   -- scrypt, salt$hash hex (api/security.py)
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
