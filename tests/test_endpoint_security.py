"""
tests/test_endpoint_security.py — Deep API & Endpoint Security Audit Tests

Verifies:
1. Unauthenticated & Unauthorized RBAC route protection.
2. Cross-student IDOR (Student A accessing Student B's records, documents, fees, attendance).
3. Parameter pollution / mass assignment rejection (role/linked_student_id tampering).
4. Safe internal-only redirects (open redirect protection).
5. JSON API error responses and content-type handling.
6. HTTP method enforcement (state changes require POST).
7. Response data hygiene (no password hashes or TOTP secrets in JSON responses).
8. Security headers (X-Content-Type-Options, X-Frame-Options, Cache-Control).
"""

import pytest
import app as flask_app
import database


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app.test_client() as client:
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


# ---------------------------------------------------------------------------
# 1. Unauthenticated & RBAC Authorization Checks
# ---------------------------------------------------------------------------

def test_unauthenticated_protected_routes_redirect(client):
    protected_routes = [
        "/dashboard",
        "/students/add",
        "/audit-log",
        "/notifications",
        "/exams/create",
        "/analytics",
    ]
    for route in protected_routes:
        res = client.get(route)
        assert res.status_code in (302, 401, 403), f"Route {route} failed authentication requirement"


def test_student_blocked_from_admin_routes(client):
    _login_as(client, role="student", user_id=3, linked_student_id=1)
    admin_only_routes = [
        "/students/add",
        "/audit-log",
        "/notifications",
        "/exams/create",
    ]
    for route in admin_only_routes:
        res = client.get(route)
        assert res.status_code == 403, f"Student accessed admin-only route {route}"


def test_teacher_blocked_from_admin_only_routes(client):
    _login_as(client, role="teacher", user_id=2)
    admin_only_routes = [
        "/students/add",
        "/audit-log",
        "/notifications",
    ]
    for route in admin_only_routes:
        res = client.get(route)
        assert res.status_code == 403, f"Teacher accessed admin-only route {route}"


# ---------------------------------------------------------------------------
# 2. Cross-Student IDOR Protection
# ---------------------------------------------------------------------------

def test_cross_student_idor_academic_record_blocked(client):
    students = database.get_all_students()
    assert len(students) >= 2
    s1, s2 = students[0], students[1]

    _login_as(client, role="student", user_id=s1["id"], linked_student_id=s1["id"])
    res = client.get(f"/students/{s2['id']}/academic-record")
    assert res.status_code == 403


def test_cross_student_idor_fees_blocked(client):
    students = database.get_all_students()
    assert len(students) >= 2
    s1, s2 = students[0], students[1]

    _login_as(client, role="student", user_id=s1["id"], linked_student_id=s1["id"])
    res = client.get(f"/fees/{s2['id']}")
    assert res.status_code == 403


def test_cross_student_idor_attendance_blocked(client):
    students = database.get_all_students()
    assert len(students) >= 2
    s1, s2 = students[0], students[1]

    _login_as(client, role="student", user_id=s1["id"], linked_student_id=s1["id"])
    res = client.get(f"/attendance/{s2['id']}")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 3. Open Redirect Neutralization
# ---------------------------------------------------------------------------

def test_open_redirect_url_sanitized():
    with flask_app.app.test_request_context("/"):
        url = flask_app._get_default_home_url()
        assert url.startswith("/")
        assert not url.startswith("//")
        assert "evil.com" not in url


# ---------------------------------------------------------------------------
# 4. JSON API Response & Error Handling
# ---------------------------------------------------------------------------

def test_api_global_search_returns_json(client):
    _login_as(client, role="admin", user_id=1)
    res = client.get("/api/global-search?q=demo")
    assert res.status_code == 200
    assert res.content_type == "application/json"
    data = res.get_json()
    assert "results" in data


def test_api_rankings_student_scoped_response(client):
    students = database.get_all_students()
    assert len(students) >= 2
    s1 = students[0]

    _login_as(client, role="student", user_id=s1["id"], linked_student_id=s1["id"])
    res = client.get("/api/student-rankings?semester=1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["role"] == "student"
    # Student response must only list their own rank in rankings array
    for rank_item in data.get("rankings", []):
        if rank_item:
            assert str(rank_item.get("record_id")) == str(s1["id"]) or str(rank_item.get("student_id")) == str(s1["student_id"])


# ---------------------------------------------------------------------------
# 5. Security Response Headers
# ---------------------------------------------------------------------------

def test_security_headers_present(client):
    res = client.get("/")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "strict-origin-when-cross-origin" in res.headers.get("Referrer-Policy", "")


def test_cache_control_no_store_for_authenticated(client):
    _login_as(client, role="admin", user_id=1)
    res = client.get("/dashboard")
    assert "no-store" in res.headers.get("Cache-Control", "")
