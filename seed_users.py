"""
seed_users.py — seeds admin, teacher, and student accounts.

This script replaces seed_admin.py. Run it once after schema.sql (fresh install)
or after migrate.py (existing install):

    python seed_users.py --dev

In production, provide explicit secure passwords via environment variables:
    SEED_ADMIN_PASSWORD=... SEED_TEACHER_PASSWORD=... SEED_STUDENT_PASSWORD=... python seed_users.py

All operations are idempotent — safe to re-run (skips existing usernames).
"""

import os
import sys
from werkzeug.security import generate_password_hash
import config
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


def seed(admin_password, teacher_password, student_password):
    """Seed user accounts with provided passwords."""
    print("Seeding users…")

    create_user("admin",   admin_password,   "admin")
    create_user("teacher", teacher_password, "teacher")

    # Link the student account to BCA2401 (Aarav Sharma — first sample row)
    stud_pk = get_student_pk("BCA2401")
    if stud_pk:
        create_user("student", student_password, "student", linked_student_id=stud_pk)
    else:
        print("  WARNING: student BCA2401 not found — "
              "run schema.sql first, then re-run seed_users.py")

    print("Done.")


if __name__ == "__main__":
    admin_pass = os.environ.get("SEED_ADMIN_PASSWORD")
    teacher_pass = os.environ.get("SEED_TEACHER_PASSWORD")
    student_pass = os.environ.get("SEED_STUDENT_PASSWORD")

    allow_demo = (
        "--dev" in sys.argv
        or os.environ.get("SEED_ALLOW_DEMO", "").lower() in ("1", "true", "yes")
        or getattr(config, "FLASK_DEBUG", False) is True
    )

    if not (admin_pass and teacher_pass and student_pass):
        if not allow_demo:
            print(
                "ERROR: Predictable development credentials cannot be seeded in production.\n"
                "To set custom production credentials, provide environment variables:\n"
                "  SEED_ADMIN_PASSWORD, SEED_TEACHER_PASSWORD, SEED_STUDENT_PASSWORD\n"
                "Or explicitly allow demo accounts for local development:\n"
                "  python seed_users.py --dev   or set SEED_ALLOW_DEMO=true\n"
            )
            sys.exit(1)
        print(
            "WARNING: Seeding default demo credentials (admin123/teacher123/student123).\n"
            "DO NOT use these credentials in a production environment!\n"
        )
        admin_pass = admin_pass or "admin123"
        teacher_pass = teacher_pass or "teacher123"
        student_pass = student_pass or "student123"

    seed(admin_pass, teacher_pass, student_pass)
