"""
Tests for 404 Not Found and 500 Internal Server Error custom handlers.
"""

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


def test_404_handler_returns_custom_page(client):
    """Accessing a non-existent URL should return custom 404 HTML and HTTP status 404."""
    response = client.get("/non-existent-page-xyz-123")
    assert response.status_code == 404
    assert b"404 Not Found" in response.data
    assert b"Page Not Found" in response.data
    assert b"The page you're looking for doesn't exist." in response.data
    assert b"Back to Dashboard" in response.data


def test_500_handler_returns_custom_page(client, monkeypatch):
    """Triggering an unhandled exception inside a route returns custom 500 page without leaking stack trace."""
    import database

    def mock_crash(*args, **kwargs):
        raise RuntimeError("Simulated database crash for testing 500 handler")

    monkeypatch.setattr(database, "get_dashboard_stats", mock_crash)
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    # Log in as admin to reach dashboard where get_dashboard_stats is called
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    response = client.get("/dashboard")
    assert response.status_code == 500
    assert b"500 Server Error" in response.data
    assert b"Server Error" in response.data
    assert b"Something went wrong on our end." in response.data
    assert b"Simulated database crash" not in response.data  # Ensure internal exception details are suppressed


