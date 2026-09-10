"""
test_password_change.py — Self-service password change tests.
"""

import os
import mysql.connector
import pytest
from werkzeug.security import check_password_hash


def _get_user_db_row(username):
    conn = mysql.connector.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


class TestPasswordChangeValidation:
    """Validation failure tests for GET/POST /change-password."""

    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/change-password", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_get_succeeds(self, admin_client):
        resp = admin_client.get("/change-password")
        assert resp.status_code == 200
        assert b"Change Password" in resp.data

    def test_wrong_current_password_rejected(self, admin_client, db):
        hash_before = _get_user_db_row("admin")["password"]

        resp = admin_client.post(
            "/change-password",
            data={
                "current_password":     "wrongpassword",
                "new_password":         "newadmin123",
                "confirm_new_password": "newadmin123",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Current password is incorrect" in resp.data

        hash_after = _get_user_db_row("admin")["password"]
        assert hash_before == hash_after, "DB password hash must not change on validation failure"

    def test_mismatched_confirm_password_rejected(self, admin_client, db):
        hash_before = _get_user_db_row("admin")["password"]

        resp = admin_client.post(
            "/change-password",
            data={
                "current_password":     "admin123",
                "new_password":         "newadmin123",
                "confirm_new_password": "differentpassword",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"do not match" in resp.data

        hash_after = _get_user_db_row("admin")["password"]
        assert hash_before == hash_after

    def test_short_new_password_rejected(self, admin_client, db):
        hash_before = _get_user_db_row("admin")["password"]

        resp = admin_client.post(
            "/change-password",
            data={
                "current_password":     "admin123",
                "new_password":         "short",
                "confirm_new_password": "short",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"at least 8 characters" in resp.data

        hash_after = _get_user_db_row("admin")["password"]
        assert hash_before == hash_after

    def test_same_new_password_rejected(self, admin_client, db):
        hash_before = _get_user_db_row("admin")["password"]

        resp = admin_client.post(
            "/change-password",
            data={
                "current_password":     "admin123",
                "new_password":         "admin123",
                "confirm_new_password": "admin123",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"must be different" in resp.data

        hash_after = _get_user_db_row("admin")["password"]
        assert hash_before == hash_after


class TestPasswordChangeSuccess:
    """Full round-trip password change tests for all 3 roles."""

    def _test_role_password_change_roundtrip(self, app, username, old_pass, new_pass):
        hash_before = _get_user_db_row(username)["password"]
        try:
            # 1. Login with old password
            authed_client = app.test_client()
            login_resp = authed_client.post(
                "/login",
                data={"username": username, "password": old_pass},
                follow_redirects=False,
            )
            assert login_resp.status_code == 302, f"Failed initial login for {username}"

            # 2. Change password
            change_resp = authed_client.post(
                "/change-password",
                data={
                    "current_password":     old_pass,
                    "new_password":         new_pass,
                    "confirm_new_password": new_pass,
                },
                follow_redirects=False,
            )
            assert change_resp.status_code == 302, f"Change password failed for {username}"
            assert "/dashboard" in change_resp.headers["Location"]

            # 3. Verify DB hash changed and matches new password
            hash_after = _get_user_db_row(username)["password"]
            assert hash_before != hash_after, f"DB password hash did not change for {username}"
            assert check_password_hash(hash_after, new_pass)

            # 4. Fresh client login attempt with OLD password fails
            fresh_client1 = app.test_client()
            old_login_resp = fresh_client1.post(
                "/login",
                data={"username": username, "password": old_pass},
                follow_redirects=True,
            )
            assert b"Invalid username or password" in old_login_resp.data

            # 5. Fresh client login attempt with NEW password succeeds
            fresh_client2 = app.test_client()
            new_login_resp = fresh_client2.post(
                "/login",
                data={"username": username, "password": new_pass},
                follow_redirects=False,
            )
            assert new_login_resp.status_code == 302
            assert "/dashboard" in new_login_resp.headers["Location"]
        finally:
            conn = mysql.connector.connect(
                host=os.environ["DB_HOST"],
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
                database=os.environ["DB_NAME"],
            )
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password = %s WHERE username = %s", (hash_before, username))
            conn.commit()
            cursor.close()
            conn.close()

    def test_admin_password_change_roundtrip(self, app, db):
        self._test_role_password_change_roundtrip(
            app, "admin", "admin123", "newadminpass123"
        )

    def test_teacher_password_change_roundtrip(self, app, db):
        self._test_role_password_change_roundtrip(
            app, "teacher", "teacher123", "newteacherpass123"
        )

    def test_student_password_change_roundtrip(self, app, db):
        self._test_role_password_change_roundtrip(
            app, "student", "student123", "newstudentpass123"
        )
