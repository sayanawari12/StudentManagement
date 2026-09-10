"""
test_csrf.py — CSRF protection enforcement.

This test overrides the default WTF_CSRF_ENABLED=False fixture to run
with CSRF enabled, verifying that:
  - POST without a csrf_token returns 400
  - POST with a valid token (scraped from the GET page) returns 302

Because this test needs CSRF ON, it creates its own app/client rather
than using the default fixtures.
"""

import re
import pytest


@pytest.fixture
def csrf_app(db):
    """Flask app with CSRF enabled (overrides default test config)."""
    from app import app as flask_app
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=True,
        SECRET_KEY="test-secret-key-not-for-production",
    )
    yield flask_app
    # Restore default test config so other fixtures are unaffected
    flask_app.config["WTF_CSRF_ENABLED"] = False


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


class TestCSRFProtection:
    def test_post_without_csrf_token_returns_400(self, csrf_client):
        """
        Posting to /login without a csrf_token field must return 400 Bad Request.
        This confirms CSRFProtect(app) is active and enforcing on all POST routes.
        """
        resp = csrf_client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing CSRF token, got {resp.status_code}"
        )

    def test_post_with_valid_csrf_token_succeeds(self, csrf_client):
        """
        POST to /login with a valid CSRF token (scraped from the GET form)
        must succeed and redirect (302) to /dashboard.
        """
        # Fetch the login page to get a real csrf_token
        get_resp = csrf_client.get("/login")
        assert get_resp.status_code == 200

        html = get_resp.data.decode("utf-8")
        match = re.search(
            r'<input[^>]+name="csrf_token"[^>]+value="([^"]+)"',
            html,
        )
        assert match, (
            "Could not find csrf_token hidden input in GET /login response. "
            "Check that login.html contains: "
            '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'
        )
        token = match.group(1)

        # POST with the scraped token — should redirect to /dashboard
        post_resp = csrf_client.post(
            "/login",
            data={
                "username":   "admin",
                "password":   "admin123",
                "csrf_token": token,
            },
            follow_redirects=False,
        )
        assert post_resp.status_code == 302, (
            f"Expected 302 redirect after valid CSRF token, got {post_resp.status_code}"
        )
        assert "/dashboard" in post_resp.headers.get("Location", ""), (
            f"Expected redirect to /dashboard, got Location={post_resp.headers.get('Location')}"
        )

    def test_empty_csrf_token_returns_400(self, csrf_client):
        """Sending csrf_token='' (present but empty) must also return 400."""
        resp = csrf_client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "csrf_token": ""},
        )
        assert resp.status_code == 400, (
            f"Expected 400 for empty CSRF token, got {resp.status_code}"
        )

    def test_invalid_csrf_token_returns_400(self, csrf_client):
        """Sending a made-up token string must return 400."""
        resp = csrf_client.post(
            "/login",
            data={
                "username":   "admin",
                "password":   "admin123",
                "csrf_token": "not-a-real-token",
            },
        )
        assert resp.status_code == 400, (
            f"Expected 400 for invalid CSRF token, got {resp.status_code}"
        )
