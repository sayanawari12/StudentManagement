"""
tests/test_final_security_audit.py — Step 2O Final End-to-End Security Verification

Comprehensive verification of:
1. End-to-end cross-student IDOR boundary isolation across all student modules.
2. State-changing HTTP method restriction (rejection of GET mutations).
3. Public QR verification endpoint information disclosure bounds.
4. Response hygiene (confidentiality of secrets, keys, and hashes).
5. Comprehensive security headers and no-store caching compliance.
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
# 1. Comprehensive Cross-Student IDOR Boundary Protection
# ---------------------------------------------------------------------------

def test_final_cross_student_idor_comprehensive_matrix(client):
    students = database.get_all_students()
    assert len(students) >= 2, "At least 2 students required for cross-student security verification"
    s1, s2 = students[0], students[1]

    _login_as(client, role="student", user_id=s1["id"], linked_student_id=s1["id"])

    # Attempting access to Student 2's resources as Student 1 -> All must return 403 Forbidden
    idor_endpoints = [
        f"/students/{s2['id']}",
        f"/students/{s2['id']}/academic-record",
        f"/students/{s2['id']}/academic-record/pdf",
        f"/attendance/{s2['id']}",
        f"/grades/{s2['id']}",
        f"/fees/{s2['id']}",
        f"/students/{s2['id']}/result-history",
        f"/students/{s2['id']}/id-card",
        f"/students/{s2['id']}/id-card/download",
        f"/students/{s2['id']}/certificate",
    ]

    for endpoint in idor_endpoints:
        res = client.get(endpoint)
        assert res.status_code == 403, f"IDOR vulnerability detected! Student 1 accessed Student 2's endpoint {endpoint}"


# ---------------------------------------------------------------------------
# 2. Public Verification Endpoint Information Scoping
# ---------------------------------------------------------------------------

def test_public_qr_verification_exposes_minimal_data_only(client):
    students = database.get_all_students()
    assert len(students) > 0
    s = students[0]

    # Public verification using VARCHAR roll number (student_id)
    res = client.get(f"/verify/student/{s['student_id']}")
    assert res.status_code == 200

    html = res.data.decode("utf-8")
    # Must contain public verification details
    assert s["student_id"] in html
    assert s["student_name"] in html

    # Must NOT expose private/sensitive fields in public view
    assert "password" not in html.lower()
    assert "secret_key" not in html.lower()
    assert "totp_secret" not in html.lower()


# ---------------------------------------------------------------------------
# 3. State-Changing Rejection on GET Requests
# ---------------------------------------------------------------------------

def test_destructive_operations_reject_get_method(client):
    _login_as(client, role="admin", user_id=1)

    # State-changing endpoints should require POST and not allow execution via GET
    post_only_routes = [
        "/students/1/delete",
        "/notices/1/delete",
        "/exams/1/delete",
        "/2fa/disable",
        "/notifications/send-fee-reminders",
        "/notifications/send-attendance-alerts",
    ]

    for route in post_only_routes:
        res = client.get(route)
        assert res.status_code == 405, f"State-changing route {route} allowed GET method execution"


# ---------------------------------------------------------------------------
# 4. Security Headers & Confidentiality Hygiene
# ---------------------------------------------------------------------------

def test_authenticated_response_security_headers_and_no_store(client):
    _login_as(client, role="admin", user_id=1)
    res = client.get("/dashboard")

    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "strict-origin-when-cross-origin" in res.headers.get("Referrer-Policy", "")
    assert "no-store" in res.headers.get("Cache-Control", "")
    assert res.headers.get("Pragma") == "no-cache"
