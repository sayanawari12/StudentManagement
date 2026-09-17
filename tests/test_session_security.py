"""
tests/test_session_security.py — Automated security tests for Step 2H Session, CSRF, & Security Headers.

Covers:
  - Cookie security attributes (HttpOnly, SameSite, Secure)
  - Session lifecycle, fixation resistance, logout invalidation, and 2FA pending isolation
  - Global CSRF token enforcement and bypass resilience on state-changing POST routes
  - Security headers (nosniff, frame options, referrer policy, permissions policy)
  - Sensitive response cache-control (no-store for authenticated pages and PDFs)
"""

import pytest
import config


class TestCookieSecurityConfig:
    """Verify Flask session cookie configuration attributes."""

    def test_session_cookie_httponly_and_samesite(self, app):
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    def test_session_cookie_secure_matches_environment(self, app):
        expected_secure = not config.FLASK_DEBUG
        assert app.config["SESSION_COOKIE_SECURE"] == expected_secure


class TestSessionLifecycleAndFixation:
    """Verify session regeneration, contents, logout invalidation, and pending 2FA isolation."""

    def test_session_fixation_resistance_on_login(self, client, db):
        # Set pre-authentication session value
        with client.session_transaction() as sess:
            sess["pre_login_tracker"] = "unauthenticated_value"

        resp = client.post(
            "/login",
            data={"username": "admin1", "password": "Sayan@@@"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

        with client.session_transaction() as sess:
            assert "pre_login_tracker" not in sess, "Pre-authentication session value must be cleared on login"
            assert sess.get("role") == "admin"
            assert sess.get("user_id") is not None

    def test_session_cleared_on_logout(self, admin_client):
        with admin_client.session_transaction() as sess:
            assert sess.get("role") == "admin"

        resp = admin_client.get("/logout", follow_redirects=True)
        assert resp.status_code == 200

        with admin_client.session_transaction() as sess:
            assert "role" not in sess
            assert "user_id" not in sess
            assert "linked_student_id" not in sess

    def test_pending_2fa_session_cannot_access_protected_routes(self, client, db):
        with client.session_transaction() as sess:
            sess["pending_2fa_user_id"] = db["users"]["admin1"]["id"]

        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


class TestCsrfEnforcementAndBypass:
    """Verify state-changing POST endpoints require valid CSRF tokens when CSRF is enabled."""

    @pytest.fixture
    def csrf_enabled_app(self, app):
        app.config["WTF_CSRF_ENABLED"] = True
        yield app
        app.config["WTF_CSRF_ENABLED"] = False

    def test_post_without_csrf_token_rejected(self, csrf_enabled_app):
        client = csrf_enabled_app.test_client()
        resp = client.post(
            "/login",
            data={
                "username": "admin1",
                "password": "Sayan@@@",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_post_with_invalid_csrf_token_rejected(self, csrf_enabled_app):
        client = csrf_enabled_app.test_client()
        resp = client.post(
            "/login",
            data={
                "csrf_token": "invalid_fake_csrf_token_12345",
                "username": "admin1",
                "password": "Sayan@@@",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400


class TestSecurityHeadersAndCacheControl:
    """Verify security headers and sensitive response cache control across pages."""

    def test_security_headers_present_on_normal_and_error_responses(self, client, admin_client):
        # 1. Normal response
        r1 = client.get("/login")
        assert r1.headers.get("X-Content-Type-Options") == "nosniff"
        assert r1.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert r1.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in r1.headers

        # 2. 404 Error response
        r2 = client.get("/nonexistent-endpoint-404")
        assert r2.status_code == 404
        assert r2.headers.get("X-Content-Type-Options") == "nosniff"
        assert r2.headers.get("X-Frame-Options") == "SAMEORIGIN"

        # 3. 403 Forbidden response
        r3 = client.get("/audit-log")
        assert r3.status_code == 302 or r3.status_code == 403

    def test_cache_control_no_store_on_authenticated_and_pdf_responses(self, admin_client, db):
        own_id = db["linked_pk"]

        # Authenticated student profile page
        r1 = admin_client.get(f"/students/{own_id}")
        assert r1.status_code == 200
        assert "no-store" in r1.headers.get("Cache-Control", "")

        # Authenticated PDF download
        r2 = admin_client.get(f"/students/{own_id}/academic-record/pdf")
        assert r2.status_code == 200
        assert "no-store" in r2.headers.get("Cache-Control", "")

    def test_static_files_do_not_force_no_store(self, client):
        r = client.get("/static/css/style.css")
        if r.status_code == 200:
            assert "no-store" not in r.headers.get("Cache-Control", "")
