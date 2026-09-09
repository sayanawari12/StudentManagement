"""
One-off helper to create the first admin account, since the app has no
signup page by design (a single-admin system doesn't need one).

Run this once after creating the database with schema.sql:
    python seed_admin.py
"""

from werkzeug.security import generate_password_hash
import database


def create_admin(username, password):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    try:
        hashed = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO admins (username, password) VALUES (%s, %s)",
            (username, hashed)
        )
        conn.commit()
        print(f"Admin '{username}' created successfully.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # Change the password below before running this in your own setup.
    create_admin("admin", "admin123")
