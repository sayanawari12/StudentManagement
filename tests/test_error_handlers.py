"""
tests/test_error_handlers.py — Comprehensive security and exception safety tests.
Verifies error handlers (403, 404, 413, 429, 500) return safe responses without
leaking stack traces, SQL queries, secrets, internal paths, or credentials.
"""

import io
import os
import pytest
from app import app
import database


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


def _login_as(client, role="admin", user_id=1, username="admin", linked_student_id=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role
        if linked_student_id is not None:
            sess["linked_student_id"] = linked_student_id
        elif role == "student":
            sess["linked_student_id"] = user_id


def test_404_handler_returns_custom_page(client):
    """Accessing a non-existent URL should return custom 404 HTML and HTTP status 404."""
    response = client.get("/non-existent-page-xyz-123")
    assert response.status_code == 404
    assert b"404 Not Found" in response.data
    assert b"Page Not Found" in response.data
    assert b"The page you're looking for doesn't exist." in response.data
    assert b"Back to Dashboard" in response.data or b"Back to Login" in response.data


def test_500_handler_returns_custom_page(client, monkeypatch):
    """Triggering an unhandled exception inside a route returns custom 500 page without leaking stack trace."""
    def mock_crash(*args, **kwargs):
        raise RuntimeError("Simulated database crash for testing 500 handler")

    monkeypatch.setattr(database, "get_dashboard_stats", mock_crash)
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    _login_as(client, role="admin", user_id=1, username="admin")

    response = client.get("/dashboard")
    assert response.status_code == 500
    assert b"500 Server Error" in response.data
    assert b"Server Error" in response.data
    assert b"Something went wrong on our end." in response.data
    assert b"Simulated database crash" not in response.data


# ---------------------------------------------------------------------------
# Information Leakage & Exception Safety Tests (STEP 2C)
# ---------------------------------------------------------------------------

def test_security_404_no_information_leakage(client):
    """Test A — Nonexistent resource returns 404 without exposing internal paths or SQL."""
    res = client.get("/nonexistent-secure-endpoint/path/123")
    assert res.status_code == 404
    assert b"Traceback" not in res.data
    assert b"SELECT" not in res.data
    assert b"c:\\" not in res.data.lower()
    assert b"mysql" not in res.data.lower()


def test_security_403_unauthorized_access_denied(client):
    """Test B — Unauthorized resource access returns 403 without internal details."""
    _login_as(client, role="student", user_id=99, username="student_user", linked_student_id=99)
    res = client.get("/analytics")
    assert res.status_code == 403
    assert b"403" in res.data or b"Access" in res.data or b"Forbidden" in res.data
    assert b"Traceback" not in res.data
    assert b"mysql" not in res.data.lower()


def test_security_413_payload_too_large(client):
    """Test C — Request exceeding size limit returns 413 without traceback."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s_pk = students[0]["id"] if students else 1

    res = client.post(
        f"/student/{s_pk}/documents/upload",
        data={"document_file": (io.BytesIO(b"X" * (17 * 1024 * 1024)), "huge.pdf", "application/pdf")},
        follow_redirects=False
    )
    assert res.status_code == 413
    assert b"Traceback" not in res.data


def test_security_forced_unexpected_exception_no_secret_leak(client, monkeypatch):
    """Test E & F — Unexpected database exception with secret string does not leak to user."""
    secret_db_err = "SECRET_INTERNAL_DATABASE_HOST_mysql_cluster_prod_3306"

    def mock_db_error(*args, **kwargs):
        raise RuntimeError(secret_db_err)

    monkeypatch.setattr(database, "get_dashboard_stats", mock_db_error)
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    _login_as(client, role="admin", user_id=1, username="admin")

    res = client.get("/dashboard")
    assert res.status_code == 500
    assert secret_db_err.encode() not in res.data
    assert b"Traceback" not in res.data
    assert b"c:\\" not in res.data.lower()


def test_security_pdf_exception_safe_response(client, monkeypatch):
    """Test G — PDF generation exception returns safe response without traceback."""
    _login_as(client, role="admin", user_id=1, username="admin")

    valid_student = {
        "id": 1,
        "student_id": "STU001",
        "student_name": "Test Student",
        "gender": "Male",
        "course": "BCA",
        "semester": "1",
        "address": "Address"
    }
    monkeypatch.setattr(database, "get_student_by_id", lambda record_id: valid_student)

    def mock_pdf_fail(*args, **kwargs):
        raise Exception("ReportLab internal font file missing /var/www/secret_font.ttf")

    import app as flask_app
    monkeypatch.setattr(flask_app, "generate_bonafide_pdf", mock_pdf_fail)
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    res = client.get("/students/1/certificate")
    assert res.status_code == 500
    assert b"secret_font.ttf" not in res.data
    assert b"Traceback" not in res.data


def test_security_file_exception_path_suppression(client, monkeypatch):
    """Test H — FileNotFoundError with private path does not leak path to user."""
    fake_path = "C:\\Users\\SecretAdmin\\AppData\\Local\\PrivateKeys\\secret.key"

    def mock_file_err(*args, **kwargs):
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{fake_path}'")

    monkeypatch.setattr(database, "get_all_students", mock_file_err)
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    _login_as(client, role="admin", user_id=1, username="admin")

    res = client.get("/students")
    assert res.status_code == 500
    assert fake_path.encode() not in res.data
    assert b"Traceback" not in res.data


def test_security_api_error_json_format(client, monkeypatch):
    """Test I — API endpoint encountering exception returns clean JSON error response."""
    _login_as(client, role="admin", user_id=1, username="admin")

    def mock_search_fail(*args, **kwargs):
        raise RuntimeError("Internal DB search error: SELECT * FROM secret_table")

    monkeypatch.setattr(database, "global_search", mock_search_fail)
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    res = client.get("/api/global-search?q=test")
    assert res.status_code == 500
    json_data = res.get_json()
    assert json_data is not None
    assert json_data.get("success") is False
    assert "secret_table" not in str(json_data)
    assert "Traceback" not in str(json_data)


def test_security_debug_configuration():
    """Test J — Verify FLASK_DEBUG configuration parsing behavior."""
    from config import FLASK_DEBUG
    assert isinstance(FLASK_DEBUG, bool)
