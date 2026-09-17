"""
update_credentials.py — Safe, idempotent migration to update demo user credentials.

This script renames and re-hashes the three default demo accounts in the
LOCAL student_management database.  It does NOT touch any other users.

Changes applied:
  admin   → admin1   (password: Sayan@@@)
  teacher → teacher1 (password: Sayan@@)
  student → student1 (password: Sayan@)

Usage (local development only):
    python update_credentials.py

Password hashing is performed by Werkzeug's generate_password_hash
(the same mechanism used throughout the application).
"""

import sys
from werkzeug.security import generate_password_hash
import config
import database


def _get_conn():
    return database.get_db_connection()


def update_user(old_username: str, new_username: str, new_password: str) -> None:
    """Rename a user and set a fresh password hash, atomically.

    Behaviour:
    - If old_username does not exist, skip (nothing to migrate).
    - If new_username already exists (rename already done), only
      update the password hash so the operation stays idempotent.
    - Passwords are never stored in plaintext; only the hash is written.
    """
    conn = _get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        # Check current state
        cursor.execute("SELECT id, username FROM users WHERE username = %s", (old_username,))
        old_row = cursor.fetchone()

        cursor.execute("SELECT id, username FROM users WHERE username = %s", (new_username,))
        new_row = cursor.fetchone()

        hashed = generate_password_hash(new_password)

        if old_row and not new_row:
            # Normal case: rename + re-hash
            cursor.execute(
                "UPDATE users SET username = %s, password = %s WHERE id = %s",
                (new_username, hashed, old_row["id"]),
            )
            conn.commit()
            print(f"  Updated: '{old_username}' → '{new_username}' (password re-hashed)")

        elif new_row:
            # Rename already done; only update the hash
            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (hashed, new_row["id"]),
            )
            conn.commit()
            print(f"  Password updated: '{new_username}' (username unchanged)")

        else:
            print(f"  Skipped: '{old_username}' not found and '{new_username}' does not exist")
    finally:
        cursor.close()
        conn.close()


def main() -> None:
    print("Updating demo user credentials…")
    print(f"  Database: {config.DB_NAME} @ {config.DB_HOST}")
    print()

    update_user("admin",   "admin1",   "Sayan@@@")
    update_user("teacher", "teacher1", "Sayan@@")
    update_user("student", "student1", "Sayan@")

    print()
    print("Done. Verify by logging in at http://127.0.0.1:5000")


if __name__ == "__main__":
    main()
