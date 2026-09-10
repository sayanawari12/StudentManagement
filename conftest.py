"""
conftest.py — pytest fixtures for the Student Management System test suite.

Test database: student_management_test  (never touches the real DB)
Each test session drops and recreates this database from schema.sql.
"""

import os
import re
from decimal import Decimal

import mysql.connector
import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Point config at the test DB BEFORE any app module is imported
# ---------------------------------------------------------------------------
os.environ.setdefault("DB_HOST",     "localhost")
os.environ.setdefault("DB_USER",     "root")
os.environ.setdefault("DB_PASSWORD", "root123")
os.environ.setdefault("DB_NAME",     "student_management_test")
os.environ.setdefault("SECRET_KEY",  "test-secret-key-not-for-production")

# Override DB_NAME unconditionally so the test DB is always used
os.environ["DB_NAME"] = "student_management_test"

import config                # noqa: E402  (must come after os.environ patch)
import database              # noqa: E402


# ---------------------------------------------------------------------------
# Low-level DB helper (bypasses database.py to run raw SQL)
# ---------------------------------------------------------------------------

def _raw_conn(db_name=None):
    """Open a raw mysql-connector connection, optionally selecting a DB."""
    kwargs = dict(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    if db_name:
        kwargs["database"] = db_name
    return mysql.connector.connect(**kwargs)


# ---------------------------------------------------------------------------
# db fixture — session-scoped: recreate test DB once per pytest run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db():
    """
    Drop, recreate, and populate student_management_test.
    Yields control, then leaves the DB in place for post-mortem inspection.
    """
    conn = _raw_conn()
    cursor = conn.cursor()
    cursor.execute("DROP DATABASE IF EXISTS student_management_test")
    cursor.execute("CREATE DATABASE student_management_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.close()
    conn.close()

    # Run schema.sql against the test DB.
    # schema.sql starts with "CREATE DATABASE IF NOT EXISTS student_management; USE student_management;"
    # We strip those two statements and run the rest against our test DB.
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        raw_sql = f.read()

    # 1. Strip single-line SQL comments (-- ... to end of line)
    sql_no_comments = re.sub(r"--[^\n]*", "", raw_sql)

    # 2. Remove the CREATE DATABASE / USE lines (test DB already exists)
    sql_body = re.sub(
        r"CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+\S+\s*;",
        "", sql_no_comments, flags=re.IGNORECASE
    )
    sql_body = re.sub(
        r"USE\s+\S+\s*;",
        "", sql_body, flags=re.IGNORECASE
    )

    conn = _raw_conn("student_management_test")
    cursor = conn.cursor()
    # Execute statement by statement (split on ";")
    for stmt in sql_body.split(";"):
        stmt = stmt.strip()
        if stmt:
            cursor.execute(stmt)
    conn.commit()
    cursor.close()
    conn.close()

    # ----------------------------------------------------------------
    # Seed known users
    # admin   → id=1, no linked_student_id
    # teacher → id=2, no linked_student_id
    # student → id=3, linked to BCA2401 (first sample student)
    # ----------------------------------------------------------------
    conn = _raw_conn("student_management_test")
    cursor = conn.cursor(dictionary=True)

    # Get the PK of BCA2401 (inserted by schema.sql sample data)
    cursor.execute("SELECT id FROM students WHERE student_id = 'BCA2401'")
    row = cursor.fetchone()
    assert row, "schema.sql sample student BCA2401 must exist"
    linked_pk = row["id"]

    # Get a second student PK (different from the linked one) for own-record tests
    cursor.execute("SELECT id FROM students WHERE student_id != 'BCA2401' LIMIT 1")
    other_row = cursor.fetchone()
    assert other_row, "schema.sql must seed at least two students"
    other_pk = other_row["id"]

    users = [
        ("admin",   "admin123",   "admin",   None),
        ("teacher", "teacher123", "teacher", None),
        ("student", "student123", "student", linked_pk),
    ]
    for username, password, role, linked_id in users:
        hashed = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, password, role, linked_student_id) VALUES (%s,%s,%s,%s)",
            (username, hashed, role, linked_id)
        )
    conn.commit()

    # Fetch the inserted user rows so tests can reference their real IDs
    cursor.execute("SELECT id, username, role, linked_student_id FROM users ORDER BY id")
    user_rows = {r["username"]: r for r in cursor.fetchall()}

    cursor.close()
    conn.close()

    yield {
        "users":      user_rows,
        "linked_pk":  linked_pk,   # students.id that "student" account is linked to
        "other_pk":   other_pk,    # a DIFFERENT student's students.id
    }


# ---------------------------------------------------------------------------
# app fixture — function-scoped, CSRF disabled by default
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def app(db):
    """Flask app configured for testing with CSRF disabled."""
    from app import app as flask_app
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key-not-for-production",
    )
    yield flask_app


@pytest.fixture(scope="function")
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Authenticated client fixtures — log in via the real /login route
# ---------------------------------------------------------------------------

def _make_authed_client(app, username, password):
    """Log in via /login and return the authenticated test client."""
    c = app.test_client()
    resp = c.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 302, (
        f"Login failed for {username!r}: got {resp.status_code}"
    )
    return c


@pytest.fixture(scope="function")
def admin_client(app, db):
    return _make_authed_client(app, "admin", "admin123")


@pytest.fixture(scope="function")
def teacher_client(app, db):
    return _make_authed_client(app, "teacher", "teacher123")


@pytest.fixture(scope="function")
def student_client(app, db):
    return _make_authed_client(app, "student", "student123")
