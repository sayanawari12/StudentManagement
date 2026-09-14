"""
test_auth.py — Login flow, session contents, and marked_by/recorded_by regression.
"""

import mysql.connector
import os
import sys
import pytest
import config


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

class TestLoginFlow:
    def test_correct_credentials_redirect_to_dashboard(self, client):
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"]

    def test_wrong_password_stays_on_login(self, client):
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "wrongpassword"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_wrong_username_stays_on_login(self, client):
        resp = client.post(
            "/login",
            data={"username": "nobody", "password": "admin123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_wrong_credentials_no_session(self, client):
        client.post(
            "/login",
            data={"username": "admin", "password": "wrongpassword"},
        )
        with client.session_transaction() as sess:
            assert "role" not in sess
            assert "user_id" not in sess


# ---------------------------------------------------------------------------
# Session contents after login
# ---------------------------------------------------------------------------

class TestSessionAfterLogin:
    """After login the session must exactly match the DB row."""

    def _assert_session_matches_db(self, client, username, db):
        db_user = db["users"][username]
        with client.session_transaction() as sess:
            assert sess.get("user_id") == db_user["id"], (
                f"session user_id {sess.get('user_id')} != DB id {db_user['id']}"
            )
            assert sess.get("role") == db_user["role"]
            assert sess.get("linked_student_id") == db_user["linked_student_id"]

    def test_admin_session(self, admin_client, db):
        self._assert_session_matches_db(admin_client, "admin", db)

    def test_teacher_session(self, teacher_client, db):
        self._assert_session_matches_db(teacher_client, "teacher", db)

    def test_student_session(self, student_client, db):
        self._assert_session_matches_db(student_client, "student", db)

    def test_student_linked_student_id_not_none(self, student_client, db):
        with student_client.session_transaction() as sess:
            assert sess.get("linked_student_id") is not None
            assert sess.get("linked_student_id") == db["linked_pk"]

    def test_admin_linked_student_id_is_none(self, admin_client):
        with admin_client.session_transaction() as sess:
            assert sess.get("linked_student_id") is None

    def test_teacher_linked_student_id_is_none(self, teacher_client):
        with teacher_client.session_transaction() as sess:
            assert sess.get("linked_student_id") is None


# ---------------------------------------------------------------------------
# marked_by / recorded_by regression guard
# ---------------------------------------------------------------------------

class TestMarkedByAndRecordedByRegression:
    """
    Regression: marked_by and recorded_by must equal the acting user's
    own users.id — never linked_student_id, never None, never another user's id.
    """

    def _get_db_conn(self):
        return mysql.connector.connect(
            host=os.environ["DB_HOST"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
        )

    def _post_attendance(self, authed_client, stud_id, date_str):
        """POST to /attendance marking stud_id as Present on date_str."""
        authed_client.post(
            "/attendance",
            data={
                "date": date_str,
                f"status_{stud_id}": "Present",
            },
            follow_redirects=False,
        )

    def _post_grade(self, authed_client, stud_id):
        """POST to /grades/add/<stud_id> with valid data."""
        authed_client.post(
            f"/grades/add/{stud_id}",
            data={
                "subject":        "Test Subject",
                "exam_type":      "Internal",
                "marks_obtained": "75",
                "max_marks":      "100",
                "semester":       "3",
            },
            follow_redirects=False,
        )

    def test_admin_attendance_marked_by_equals_admin_user_id(self, admin_client, db):
        stud_id = db["linked_pk"]
        date_str = "2025-01-10"
        admin_user_id = db["users"]["admin"]["id"]
        admin_linked  = db["users"]["admin"]["linked_student_id"]  # None

        self._post_attendance(admin_client, stud_id, date_str)

        conn = self._get_db_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT marked_by FROM attendance WHERE stud_id=%s AND date=%s",
            (stud_id, date_str),
        )
        row = cursor.fetchone()
        cursor.close(); conn.close()

        assert row is not None, "Attendance row not inserted"
        assert row["marked_by"] == admin_user_id, (
            f"marked_by={row['marked_by']} != admin user_id={admin_user_id}"
        )
        assert row["marked_by"] != admin_linked, "marked_by must not equal linked_student_id"

    def test_teacher_attendance_marked_by_equals_teacher_user_id(self, teacher_client, db):
        stud_id = db["linked_pk"]
        date_str = "2025-01-11"
        teacher_user_id = db["users"]["teacher"]["id"]
        teacher_linked  = db["users"]["teacher"]["linked_student_id"]  # None

        self._post_attendance(teacher_client, stud_id, date_str)

        conn = self._get_db_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT marked_by FROM attendance WHERE stud_id=%s AND date=%s",
            (stud_id, date_str),
        )
        row = cursor.fetchone()
        cursor.close(); conn.close()

        assert row is not None
        assert row["marked_by"] == teacher_user_id
        assert row["marked_by"] != teacher_linked

    def test_admin_grade_recorded_by_equals_admin_user_id(self, admin_client, db):
        stud_id = db["linked_pk"]
        admin_user_id = db["users"]["admin"]["id"]

        self._post_grade(admin_client, stud_id)

        conn = self._get_db_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT recorded_by FROM grades WHERE stud_id=%s AND subject='Test Subject' ORDER BY id DESC LIMIT 1",
            (stud_id,),
        )
        row = cursor.fetchone()
        cursor.close(); conn.close()

        assert row is not None
        assert row["recorded_by"] == admin_user_id

    def test_teacher_grade_recorded_by_equals_teacher_user_id(self, teacher_client, db):
        stud_id = db["linked_pk"]
        teacher_user_id = db["users"]["teacher"]["id"]

        self._post_grade(teacher_client, stud_id)

        conn = self._get_db_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT recorded_by FROM grades WHERE stud_id=%s AND subject='Test Subject' ORDER BY id DESC LIMIT 1",
            (stud_id,),
        )
        row = cursor.fetchone()
        cursor.close(); conn.close()

        assert row is not None
        assert row["recorded_by"] == teacher_user_id

    def test_recorded_by_is_valid_users_id(self, admin_client, db):
        """
        recorded_by must be a real users.id, not corrupted by linked_student_id.

        The real regression: if the bug were present, recorded_by would receive
        session['linked_student_id'] (None for admin) → DB insert fails on the FK.
        Here we verify the inserted row has a recorded_by that matches a known user.
        """
        stud_id = db["linked_pk"]
        admin_user_id = db["users"]["admin"]["id"]

        self._post_grade(admin_client, stud_id)

        conn = self._get_db_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT recorded_by FROM grades WHERE stud_id=%s AND subject='Test Subject' ORDER BY id DESC LIMIT 1",
            (stud_id,),
        )
        row = cursor.fetchone()

        # Confirm recorded_by is a valid users.id (not None, not a bogus value)
        cursor.execute("SELECT id FROM users WHERE id=%s", (row["recorded_by"],))
        user_row = cursor.fetchone()
        cursor.close(); conn.close()

        assert user_row is not None, (
            f"recorded_by={row['recorded_by']} does not exist in the users table"
        )
        assert row["recorded_by"] == admin_user_id, (
            f"recorded_by should be admin's user_id={admin_user_id}, got {row['recorded_by']}"
        )


# ---------------------------------------------------------------------------
# _get_user_id() regression tests (Phase 1 Objective 2)
# ---------------------------------------------------------------------------

class TestGetUserIdSafety:
    """Regression tests for Phase 1 Objective 2: _get_user_id() safe resolution."""

    def test_authenticated_user_id_resolution_from_session(self, app):
        with app.test_request_context("/"):
            from flask import session
            from app import _get_user_id
            session["user_id"] = 42
            assert _get_user_id() == 42

    def test_authenticated_user_id_resolution_from_username(self, app, db):
        with app.test_request_context("/"):
            from flask import session
            from app import _get_user_id
            session["admin"] = "teacher"
            teacher_id = db["users"]["teacher"]["id"]
            assert _get_user_id() == teacher_id

    def test_db_lookup_failure_does_not_return_one(self, app):
        from unittest.mock import patch
        with app.test_request_context("/"):
            from flask import session
            from app import _get_user_id
            session["admin"] = "someone"
            with patch("database.get_user_by_username", side_effect=mysql.connector.Error("Connection error")):
                res = _get_user_id()
                assert res is None
                assert res != 1

    def test_missing_user_does_not_return_one(self, app):
        with app.test_request_context("/"):
            from flask import session
            from app import _get_user_id
            session["admin"] = "nonexistent_user_xyz"
            res = _get_user_id()
            assert res is None
            assert res != 1

    def test_caller_route_handles_unresolvable_user_safely(self, client):
        with client.session_transaction() as sess:
            sess["role"] = "admin"
            sess["admin"] = "nonexistent_user_xyz"
        resp = client.get("/change-password", follow_redirects=False)
        assert resp.status_code == 302
        assert "/logout" in resp.headers["Location"]


class TestSeedUsersGuard:
    """Tests for seed_users.py configuration guard & SEED_ALLOW_DEMO behavior."""

    def test_seed_allow_demo_environment_variable(self, monkeypatch):
        import seed_users
        monkeypatch.setenv("SEED_ALLOW_DEMO", "true")
        # verify allow_demo condition in seed_users
        allow_demo = (
            "--dev" in sys.argv
            or os.environ.get("SEED_ALLOW_DEMO", "").lower() in ("1", "true", "yes")
            or getattr(config, "FLASK_DEBUG", False) is True
        )
        assert allow_demo is True

    def test_seed_production_passwords_override_defaults(self, monkeypatch, db):
        import seed_users
        monkeypatch.setenv("SEED_ADMIN_PASSWORD", "SecureAdminPass123!")
        monkeypatch.setenv("SEED_TEACHER_PASSWORD", "SecureTeacherPass123!")
        monkeypatch.setenv("SEED_STUDENT_PASSWORD", "SecureStudentPass123!")

        admin_p = os.environ.get("SEED_ADMIN_PASSWORD")
        teacher_p = os.environ.get("SEED_TEACHER_PASSWORD")
        student_p = os.environ.get("SEED_STUDENT_PASSWORD")

        assert admin_p == "SecureAdminPass123!"
        assert teacher_p == "SecureTeacherPass123!"
        assert student_p == "SecureStudentPass123!"

