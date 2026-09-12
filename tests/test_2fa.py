"""
test_2fa.py — Tests for TOTP-based Two-Factor Authentication.

Covers:
  - Setup flow: GET renders QR; POST with correct code enables 2FA (DB persisted);
    POST with wrong code does not enable it.
  - Login flow: user with 2FA enabled is redirected to /login/2fa after correct
    username/password; correct code completes login; wrong code does not; 5
    consecutive wrong codes clear the pending session.
  - Disable flow: correct current password disables 2FA; wrong password does not.
  - Regression: user WITHOUT 2FA logs in exactly as before.

Note: pyotp.TOTP(secret).now() is used to generate valid codes dynamically so
      tests never rely on hardcoded strings.
"""

import pyotp
import pytest
import database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(client, url, **kwargs):
    return client.get(url, follow_redirects=False, **kwargs)


def post(client, url, data=None, **kwargs):
    return client.post(url, data=data or {}, follow_redirects=False, **kwargs)


def assert_redirected_to(resp, path_fragment):
    assert resp.status_code in (301, 302), f"Expected redirect, got {resp.status_code}"
    assert path_fragment in resp.headers.get("Location", ""), (
        f"Expected redirect to contain {path_fragment!r}, got {resp.headers.get('Location')}"
    )


def _reset_all(db):
    """Disable 2FA for every test user so no state leaks between tests."""
    for username in ("admin", "teacher", "student"):
        user_id = db["users"][username]["id"]
        database.disable_user_totp(user_id)


@pytest.fixture(autouse=True)
def reset_2fa_state(db):
    """Ensure 2FA is fully off for all test users before AND after every test
    in this module.  This prevents state from one test (e.g. enabling 2FA for
    teacher) from breaking teacher_client fixtures used by other tests or other
    test files that run after test_2fa.py."""
    _reset_all(db)
    yield
    _reset_all(db)


def _enable_2fa_for_user(user_id):
    """Helper: programmatically enable 2FA for a test user and return the secret."""
    secret = pyotp.random_base32()
    database.set_user_totp_secret(user_id, secret)
    database.enable_user_totp(user_id)
    return secret


def _fresh_authed_client(app, username, password):
    """Log in via /login and return (client, resp) — for regression tests."""
    c = app.test_client()
    resp = c.post("/login", data={"username": username, "password": password},
                  follow_redirects=False)
    return c, resp


# ===========================================================================
# Setup flow  (GET/POST /2fa/setup)
# ===========================================================================

class TestTotpSetupFlow:

    def test_get_setup_renders_200(self, admin_client):
        resp = get(admin_client, "/2fa/setup")
        assert resp.status_code == 200

    def test_get_setup_contains_qr_image(self, admin_client):
        resp = get(admin_client, "/2fa/setup")
        body = resp.data.decode("utf-8")
        assert "data:image/png;base64," in body

    def test_get_setup_contains_secret_text(self, admin_client, db):
        resp = get(admin_client, "/2fa/setup")
        body = resp.data.decode("utf-8")
        # After GET, a totp_secret should have been stored in the DB
        admin_id = db["users"]["admin"]["id"]
        user = database.get_user_by_id(admin_id)
        assert user["totp_secret"] is not None
        assert user["totp_secret"] in body

    def test_post_correct_code_enables_2fa(self, admin_client, db):
        # Trigger GET first so a secret is generated and stored
        get(admin_client, "/2fa/setup")
        admin_id = db["users"]["admin"]["id"]
        user = database.get_user_by_id(admin_id)
        secret = user["totp_secret"]
        assert secret is not None

        # Generate a valid code and POST it
        code = pyotp.TOTP(secret).now()
        resp = post(admin_client, "/2fa/setup", data={"code": code})
        assert_redirected_to(resp, "/dashboard")

        # DB must reflect totp_enabled = True
        updated = database.get_user_by_id(admin_id)
        assert updated["totp_enabled"] is True or updated["totp_enabled"] == 1

    def test_post_wrong_code_does_not_enable_2fa(self, teacher_client, db):
        get(teacher_client, "/2fa/setup")
        teacher_id = db["users"]["teacher"]["id"]

        resp = post(teacher_client, "/2fa/setup", data={"code": "000000"})
        # Should re-render (200), not redirect
        assert resp.status_code == 200

        updated = database.get_user_by_id(teacher_id)
        assert not updated["totp_enabled"]

    def test_get_setup_when_already_enabled_shows_disable_state(self, admin_client, db):
        admin_id = db["users"]["admin"]["id"]
        _enable_2fa_for_user(admin_id)

        resp = get(admin_client, "/2fa/setup")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Should show the disable form, not a QR code
        assert "Disable" in body or "disable" in body
        # Should NOT show a fresh QR for an already-enabled account
        # (qr_data_uri is None when already enabled)
        # The template only embeds the img tag when qr_data_uri is set
        assert "totp-qr-image" not in body

    def test_student_can_access_setup(self, student_client):
        resp = get(student_client, "/2fa/setup")
        assert resp.status_code == 200

    def test_anonymous_setup_redirects_to_login(self, client):
        resp = get(client, "/2fa/setup")
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers.get("Location", "")


# ===========================================================================
# Login flow with 2FA enabled
# ===========================================================================

class TestTotpLoginFlow:

    def test_user_with_2fa_redirected_to_verify_page(self, app, db):
        """After correct username+password, land at /login/2fa not /dashboard."""
        teacher_id = db["users"]["teacher"]["id"]
        secret = _enable_2fa_for_user(teacher_id)

        c, resp = _fresh_authed_client(app, "teacher", "teacher123")
        assert_redirected_to(resp, "/login/2fa")
        # Full session must NOT be set yet
        with c.session_transaction() as sess:
            assert "role" not in sess
            assert sess.get("pending_2fa_user_id") == teacher_id

    def test_correct_code_completes_login(self, app, db):
        teacher_id = db["users"]["teacher"]["id"]
        secret = _enable_2fa_for_user(teacher_id)

        c, _ = _fresh_authed_client(app, "teacher", "teacher123")

        code = pyotp.TOTP(secret).now()
        resp = c.post("/login/2fa", data={"code": code}, follow_redirects=False)
        assert_redirected_to(resp, "/dashboard")

        # Full session is now set
        with c.session_transaction() as sess:
            assert sess.get("role") == "teacher"
            assert "pending_2fa_user_id" not in sess

    def test_wrong_code_does_not_complete_login(self, app, db):
        teacher_id = db["users"]["teacher"]["id"]
        secret = _enable_2fa_for_user(teacher_id)

        c, _ = _fresh_authed_client(app, "teacher", "teacher123")
        resp = c.post("/login/2fa", data={"code": "000000"}, follow_redirects=False)
        # Re-renders the form (200)
        assert resp.status_code == 200

        with c.session_transaction() as sess:
            assert "role" not in sess
            assert "pending_2fa_user_id" in sess

    def test_five_wrong_codes_clears_pending_session(self, app, db):
        teacher_id = db["users"]["teacher"]["id"]
        secret = _enable_2fa_for_user(teacher_id)

        c, _ = _fresh_authed_client(app, "teacher", "teacher123")

        for _ in range(5):
            resp = c.post("/login/2fa", data={"code": "000000"}, follow_redirects=False)

        # After the 5th failure we should be redirected back to login
        assert_redirected_to(resp, "/login")

        with c.session_transaction() as sess:
            assert "pending_2fa_user_id" not in sess
            assert "role" not in sess

    def test_login_2fa_without_pending_redirects_to_login(self, client):
        resp = get(client, "/login/2fa")
        assert_redirected_to(resp, "/login")

    def test_get_login_2fa_renders_verify_form(self, app, db):
        teacher_id = db["users"]["teacher"]["id"]
        _enable_2fa_for_user(teacher_id)

        c, _ = _fresh_authed_client(app, "teacher", "teacher123")
        resp = c.get("/login/2fa", follow_redirects=False)
        assert resp.status_code == 200
        assert b"code" in resp.data


# ===========================================================================
# Disable flow  (POST /2fa/disable)
# ===========================================================================

class TestTotpDisableFlow:

    def test_correct_password_disables_2fa(self, admin_client, db):
        admin_id = db["users"]["admin"]["id"]
        _enable_2fa_for_user(admin_id)

        resp = post(admin_client, "/2fa/disable", data={"current_password": "admin123"})
        assert_redirected_to(resp, "/dashboard")

        updated = database.get_user_by_id(admin_id)
        assert not updated["totp_enabled"]
        assert updated["totp_secret"] is None

    def test_wrong_password_does_not_disable_2fa(self, admin_client, db):
        admin_id = db["users"]["admin"]["id"]
        _enable_2fa_for_user(admin_id)

        resp = post(admin_client, "/2fa/disable", data={"current_password": "wrongpass"})
        assert_redirected_to(resp, "/2fa/setup")

        updated = database.get_user_by_id(admin_id)
        assert updated["totp_enabled"] is True or updated["totp_enabled"] == 1

    def test_disable_requires_login(self, client):
        resp = post(client, "/2fa/disable", data={"current_password": "anything"})
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers.get("Location", "")


# ===========================================================================
# Regression — user WITHOUT 2FA logs in exactly as before
# ===========================================================================

class TestNon2FALoginRegression:

    def test_user_without_2fa_goes_straight_to_dashboard(self, app, db):
        """Existing behavior: no 2FA = direct session set on login."""
        # Ensure student has no 2FA (it starts disabled by default)
        student_id = db["users"]["student"]["id"]
        database.disable_user_totp(student_id)   # idempotent

        c, resp = _fresh_authed_client(app, "student", "student123")
        assert_redirected_to(resp, "/dashboard")

        with c.session_transaction() as sess:
            assert sess.get("role") == "student"
            assert "pending_2fa_user_id" not in sess

    def test_admin_without_2fa_goes_straight_to_dashboard(self, app, db):
        admin_id = db["users"]["admin"]["id"]
        database.disable_user_totp(admin_id)

        c, resp = _fresh_authed_client(app, "admin", "admin123")
        assert_redirected_to(resp, "/dashboard")

        with c.session_transaction() as sess:
            assert sess.get("role") == "admin"


# ===========================================================================
# database.py unit tests (no HTTP)
# ===========================================================================

class TestTotpDatabaseFunctions:

    def test_set_totp_secret_stores_secret(self, db):
        admin_id = db["users"]["admin"]["id"]
        secret = pyotp.random_base32()
        database.set_user_totp_secret(admin_id, secret)

        user = database.get_user_by_id(admin_id)
        assert user["totp_secret"] == secret
        assert not user["totp_enabled"]

    def test_enable_totp_sets_flag(self, db):
        admin_id = db["users"]["admin"]["id"]
        secret = pyotp.random_base32()
        database.set_user_totp_secret(admin_id, secret)
        database.enable_user_totp(admin_id)

        user = database.get_user_by_id(admin_id)
        assert user["totp_enabled"] is True or user["totp_enabled"] == 1

    def test_disable_totp_clears_secret_and_flag(self, db):
        admin_id = db["users"]["admin"]["id"]
        secret = pyotp.random_base32()
        database.set_user_totp_secret(admin_id, secret)
        database.enable_user_totp(admin_id)
        database.disable_user_totp(admin_id)

        user = database.get_user_by_id(admin_id)
        assert not user["totp_enabled"]
        assert user["totp_secret"] is None
