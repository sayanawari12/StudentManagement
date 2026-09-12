"""
tests/test_login_lockout.py — Tests for Account Lockout & Login Rate Limiting.

Covers:
  - 5 consecutive wrong passwords for real username -> 5th flashes lockout message.
  - 6th attempt (even with CORRECT password) is rejected with "Account locked" message, session not set.
  - Expired lockout (locked_until in past) -> correct password succeeds and resets counters.
  - Login success after 1-4 failures resets failed_login_attempts back to 0.
  - Non-existent username does not crash or create phantom state.
  - "Too many failed attempts" flash appears ONLY on the 5th attempt, not attempts 1-4.
"""

import datetime
import pytest
import database


class TestAccountLockout:
    def test_five_failed_attempts_triggers_lockout(self, client, db):
        # Clean state for admin
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE username = 'admin'")
        conn.commit()
        cursor.close()
        conn.close()

        # Attempts 1 to 4: should receive generic error message
        for i in range(1, 5):
            resp = client.post("/login", data={"username": "admin", "password": "wrong_password"}, follow_redirects=True)
            assert resp.status_code == 200
            assert b"Invalid username or password." in resp.data
            assert b"Too many failed attempts" not in resp.data

        # Attempt 5: triggers lockout
        resp5 = client.post("/login", data={"username": "admin", "password": "wrong_password"}, follow_redirects=True)
        assert resp5.status_code == 200
        assert b"Too many failed attempts. Account locked for 15 minutes." in resp5.data

        # Verify DB state
        user = database.get_user_by_username("admin")
        assert user["failed_login_attempts"] == 5
        assert user["locked_until"] is not None
        assert user["locked_until"] > datetime.datetime.now()

        # Attempt 6: even with CORRECT password, login is rejected
        resp6 = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
        assert resp6.status_code == 200
        assert b"Account locked." in resp6.data
        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_lockout_expiry_allows_login(self, client, db):
        # Manually set locked_until to 1 minute in the past
        past_time = datetime.datetime.now() - datetime.timedelta(minutes=1)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET failed_login_attempts = 5, locked_until = %s WHERE username = 'admin'",
            (past_time,)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Attempt with correct password should succeed
        resp = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers.get("Location", "") or "/login/2fa" in resp.headers.get("Location", "")

        # Verify counters reset in DB
        user = database.get_user_by_username("admin")
        assert user["failed_login_attempts"] == 0
        assert user["locked_until"] is None

    def test_successful_login_resets_partial_failed_attempts(self, client, db):
        # Clean state for teacher
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE username = 'teacher'")
        conn.commit()
        cursor.close()
        conn.close()

        # 3 failed attempts
        for _ in range(3):
            client.post("/login", data={"username": "teacher", "password": "wrong_password"}, follow_redirects=True)

        user_before = database.get_user_by_username("teacher")
        assert user_before["failed_login_attempts"] == 3

        # Successful login
        resp = client.post("/login", data={"username": "teacher", "password": "teacher123"}, follow_redirects=False)
        assert resp.status_code == 302

        user_after = database.get_user_by_username("teacher")
        assert user_after["failed_login_attempts"] == 0
        assert user_after["locked_until"] is None

    def test_nonexistent_username_does_not_crash_or_create_state(self, client, db):
        resp = client.post(
            "/login",
            data={"username": "non_existent_ghost_user_9999", "password": "wrong_password"},
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"Invalid username or password." in resp.data
        assert database.get_user_by_username("non_existent_ghost_user_9999") is None


class TestIpRateLimiting:
    def test_ip_rate_limiting_triggers_429(self, app, client):
        from app import limiter
        limiter.enabled = True
        try:
            responses = []
            for _ in range(11):
                resp = client.get("/login")
                responses.append(resp.status_code)
            assert 429 in responses
        finally:
            limiter.enabled = False
