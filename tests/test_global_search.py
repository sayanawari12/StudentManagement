"""
tests/test_global_search.py — Comprehensive security, RBAC and functional test suite
for Global Search Module.
"""

import pytest
from unittest.mock import patch

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
# 1. Admin Module Search Tests
# ---------------------------------------------------------------------------

def test_admin_search_students(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    assert len(students) > 0
    target_student = students[0]

    # Search by student_name
    res = client.get(f"/api/global-search?q={target_student['student_name'][:4]}")
    assert res.status_code == 200
    data = res.get_json()
    assert "results" in data
    assert len(data["results"]["students"]) > 0
    first_stud = data["results"]["students"][0]
    assert f"/students/{target_student['id']}" in first_stud["url"]


def test_admin_search_exams(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=Internal")
    assert res.status_code == 200
    data = res.get_json()
    assert "exams" in data["results"]


def test_admin_search_results(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=BCA")
    assert res.status_code == 200
    data = res.get_json()
    assert "results" in data["results"]


def test_admin_search_fees(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=Fee")
    assert res.status_code == 200
    data = res.get_json()
    assert "fees" in data["results"]


def test_admin_search_notices(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=Notice")
    assert res.status_code == 200
    data = res.get_json()
    assert "notices" in data["results"]


def test_admin_search_certificates(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=Bonafide")
    assert res.status_code == 200
    data = res.get_json()
    assert "certificates" in data["results"]


def test_admin_search_audit_logs(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=Marked")
    assert res.status_code == 200
    data = res.get_json()
    assert "audit_logs" in data["results"]


# ---------------------------------------------------------------------------
# 2. Student ID Direct Navigation & Prioritization
# ---------------------------------------------------------------------------

def test_exact_student_id_search_prioritized(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    assert len(students) > 0
    target_student = students[0]
    roll_no = target_student["student_id"]

    res = client.get(f"/api/global-search?q={roll_no}")
    assert res.status_code == 200
    data = res.get_json()
    stud_results = data["results"]["students"]
    assert len(stud_results) > 0
    # Top result must match target student
    assert stud_results[0]["student_id"] == roll_no
    assert stud_results[0]["url"] == f"/students/{target_student['id']}"


def test_student_result_uses_correct_record_id(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    target_student = students[0]

    res = client.get(f"/api/global-search?q={target_student['student_id']}")
    data = res.get_json()
    stud_item = data["results"]["students"][0]
    # record_id must be integer PK from database, not public student_id string
    assert stud_item["url"] == f"/students/{target_student['id']}"


# ---------------------------------------------------------------------------
# 3. Query Edge Cases (Partial, Case-Insensitive, Trim, Empty, Short)
# ---------------------------------------------------------------------------

def test_partial_student_name_search(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    target = students[0]["student_name"]
    partial_q = target[:3]

    res = client.get(f"/api/global-search?q={partial_q}")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["results"]["students"]) > 0


def test_case_insensitive_search(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    target = students[0]["student_name"]

    res_lower = client.get(f"/api/global-search?q={target.lower()}")
    res_upper = client.get(f"/api/global-search?q={target.upper()}")
    assert res_lower.status_code == 200
    assert res_upper.status_code == 200
    assert len(res_lower.get_json()["results"]["students"]) == len(res_upper.get_json()["results"]["students"])


def test_whitespace_trimming(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=%20%20BCA%20%20")
    assert res.status_code == 200
    data = res.get_json()
    assert data["query"] == "BCA"


def test_empty_query_handled_safely(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=")
    assert res.status_code == 200
    data = res.get_json()
    assert data["query"] == ""
    assert data["results"]["students"] == []


def test_short_query_handled_safely(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=a")
    assert res.status_code == 200
    data = res.get_json()
    assert data["results"]["students"] == []


def test_no_result_query_works(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=NonExistentTerm99999")
    assert res.status_code == 200
    data = res.get_json()
    for cat, items in data["results"].items():
        assert items == []


# ---------------------------------------------------------------------------
# 4. RBAC & Data Isolation Security Tests
# ---------------------------------------------------------------------------

def test_student_cannot_enumerate_other_students(client):
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else s1

    # Log in as s1
    _login_as(client, role="student", user_id=999, username="student_user", linked_student_id=s1["id"])

    if s1["id"] != s2["id"]:
        # Student searching s2's name/ID gets 0 student results for s2
        res = client.get(f"/api/global-search?q={s2['student_name']}")
        assert res.status_code == 200
        data = res.get_json()
        matching_ids = [s["id"] for s in data["results"]["students"]]
        assert s2["id"] not in matching_ids


def test_student_cannot_search_other_student_results(client):
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else s1

    _login_as(client, role="student", user_id=999, username="student_user", linked_student_id=s1["id"])
    if s1["id"] != s2["id"]:
        res = client.get(f"/api/global-search?q={s2['student_id']}")
        data = res.get_json()
        assert data["results"]["results"] == []


def test_student_cannot_search_other_student_fees(client):
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else s1

    _login_as(client, role="student", user_id=999, username="student_user", linked_student_id=s1["id"])
    if s1["id"] != s2["id"]:
        res = client.get(f"/api/global-search?q={s2['student_id']}")
        data = res.get_json()
        assert data["results"]["fees"] == []


def test_student_cannot_search_other_student_certificates(client):
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else s1

    _login_as(client, role="student", user_id=999, username="student_user", linked_student_id=s1["id"])
    if s1["id"] != s2["id"]:
        res = client.get(f"/api/global-search?q={s2['student_name']}")
        data = res.get_json()
        assert data["results"]["certificates"] == []


def test_teacher_cannot_receive_fees(client):
    _login_as(client, role="teacher", user_id=2, username="teacher_user")
    res = client.get("/api/global-search?q=Fee")
    assert res.status_code == 200
    data = res.get_json()
    assert data["results"]["fees"] == []


def test_teacher_cannot_receive_audit_logs(client):
    _login_as(client, role="teacher", user_id=2, username="teacher_user")
    res = client.get("/api/global-search?q=Marked")
    assert res.status_code == 200
    data = res.get_json()
    assert data["results"]["audit_logs"] == []


# ---------------------------------------------------------------------------
# 5. Injection & Sensitive Data Security Tests
# ---------------------------------------------------------------------------

def test_sql_injection_payload_handled_safely(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    payload = "' OR '1'='1"
    res = client.get(f"/api/global-search?q={payload}")
    assert res.status_code == 200
    data = res.get_json()
    # Payload should be matched literally as string, not execute SQL injection
    assert isinstance(data["results"], dict)


def test_like_wildcard_handling_safe(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res_percent = client.get("/api/global-search?q=%25")
    res_underscore = client.get("/api/global-search?q=_")
    assert res_percent.status_code == 200
    assert res_underscore.status_code == 200


def test_sensitive_info_not_exposed(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=admin")
    assert res.status_code == 200
    data_str = res.get_data(as_text=True)
    assert "password" not in data_str.lower()
    assert "totp_secret" not in data_str.lower()


def test_unauthorized_documents_not_exposed(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    res = client.get("/api/global-search?q=doc_")
    assert res.status_code == 200
    data_str = res.get_data(as_text=True)
    assert "uploads/documents" not in data_str


def test_unauthenticated_request_redirects(client):
    res = client.get("/api/global-search?q=test")
    assert res.status_code == 302


def test_search_result_links_use_existing_routes(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    res = client.get(f"/api/global-search?q={s['student_name']}")
    data = res.get_json()
    for cat, items in data["results"].items():
        for item in items:
            assert "url" in item
            assert item["url"].startswith("/")


def test_student_role_can_search_own_data(client):
    students = database.get_all_students()
    s = students[0]

    _login_as(client, role="student", user_id=999, username="student_user", linked_student_id=s["id"])
    res = client.get(f"/api/global-search?q={s['student_name'][:3]}")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["results"]["students"]) == 1
    assert data["results"]["students"][0]["id"] == s["id"]


def test_global_search_helper_unit_tests():
    data = database.global_search("BCA", "admin", 1)
    assert isinstance(data, dict)
    assert "query" in data
    assert "results" in data
    assert "students" in data["results"]
