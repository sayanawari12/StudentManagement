"""
seed_users.py — seeds admin, teacher, and student accounts.

This script replaces seed_admin.py. Run it once after schema.sql (fresh install)
or after migrate.py (existing install):

    python seed_users.py

Accounts created:
    admin   / admin123   — role=admin,   can do everything
    teacher / teacher123 — role=teacher, can view students + mark attendance
    student / student123 — role=student, linked to student BCA2401 (Aarav Sharma)

All operations are idempotent — safe to re-run (skips existing usernames).
"""

from werkzeug.security import generate_password_hash
import database
import mysql.connector


def create_user(username, password, role, linked_student_id=None):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    try:
        hashed = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, password, role, linked_student_id) "
            "VALUES (%s, %s, %s, %s)",
            (username, hashed, role, linked_student_id)
        )
        conn.commit()
        print(f"  Created: {username!r} (role={role})")
    except mysql.connector.IntegrityError:
        print(f"  Skipped: {username!r} already exists")
    finally:
        cursor.close()
        conn.close()


def get_student_pk(student_id_roll):
    """Return the INT primary key for a given VARCHAR roll number."""
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id FROM students WHERE student_id = %s", (student_id_roll,)
        )
        row = cursor.fetchone()
        return row["id"] if row else None
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    print("Seeding users…")

    create_user("admin",   "admin123",   "admin")
    create_user("teacher", "teacher123", "teacher")

    # Link the student account to BCA2401 (Aarav Sharma — first sample row)
    stud_pk = get_student_pk("BCA2401")
    if stud_pk:
        create_user("student", "student123", "student", linked_student_id=stud_pk)
    else:
        print("  WARNING: student BCA2401 not found — "
              "run schema.sql first, then re-run seed_users.py")

    print("Done.")
