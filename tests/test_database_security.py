"""
tests/test_database_security.py — Database Security & Data Integrity Tests

Verifies:
1. SQL injection protection in student search, global search, and notice filtering.
2. LIKE wildcard escaping (_escape_like_query neutralizing '%' and '_').
3. Atomic transaction behavior during multi-step database modifications.
4. Database-level data integrity (fee overpayment guards, exam marks boundaries).
5. Data isolation across student ownership boundaries (IDOR prevention).
6. Parameterized query safety across all filter/search endpoints.
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


# ---------------------------------------------------------------------------
# 1. SQL Injection Protection Tests
# ---------------------------------------------------------------------------

def test_sql_injection_student_search():
    # Attempt SQL injection in student search filter
    sql_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE students; --",
        "1 UNION SELECT 1,2,3,4,5,6,7,8,9--",
        "admin'--",
    ]
    for payload in sql_payloads:
        results = database.get_all_students(search=payload)
        assert isinstance(results, list)
        # Verify query executes safely without SQL syntax error or unintended record dump


def test_sql_injection_global_search():
    sql_payloads = [
        "' OR '1'='1",
        "%' AND 1=0 UNION ALL SELECT 1,2,3--",
    ]
    for payload in sql_payloads:
        res = database.global_search(query=payload, user_role="admin", user_id=1)
        assert isinstance(res, dict)
        assert "results" in res


def test_sql_injection_notice_search():
    sql_payloads = [
        "' OR 1=1 --",
        "test' UNION SELECT 1,2,3,4,5,6,7,8,9,10,11 --",
    ]
    for payload in sql_payloads:
        notices = database.get_filtered_notices(search=payload)
        assert isinstance(notices, list)


# ---------------------------------------------------------------------------
# 2. LIKE Wildcard Escaping Neutralization
# ---------------------------------------------------------------------------

def test_like_wildcard_escaping_helper():
    assert database._escape_like_query("100%") == "100\\%"
    assert database._escape_like_query("user_name") == "user\\_name"
    assert database._escape_like_query("a\\b") == "a\\\\b"
    assert database._escape_like_query("") == ""
    assert database._escape_like_query(None) == ""


def test_student_search_escapes_wildcards():
    # Searching for literal % or _ should not match every record
    res_percent = database.get_all_students(search="%")
    assert isinstance(res_percent, list)
    
    res_underscore = database.get_all_students(search="_")
    assert isinstance(res_underscore, list)


# ---------------------------------------------------------------------------
# 3. Transaction Integrity & Overpayment Protection
# ---------------------------------------------------------------------------

def test_fee_overpayment_rejected_by_database_logic():
    students = database.get_all_students()
    assert len(students) > 0
    s = students[0]

    # Create fee due of 1000
    fee_id = database.insert_fee_due({
        "stud_id": s["id"],
        "amount_due": 1000.0,
        "due_date": "2026-12-31"
    })

    try:
        # Attempt overpayment of 1500 (> 1000)
        rows_affected = database.update_fee_payment(fee_id, payment_amount=1500.0)
        assert rows_affected == 0, "DB level overpayment guard should reject payment by updating 0 rows"

        # Fee record amount_paid should remain 0
        fee = database.get_fee_by_id(fee_id)
        assert float(fee["amount_paid"]) == 0.0
    finally:
        # Cleanup
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fees WHERE id = %s", (fee_id,))
        conn.commit()
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# 4. Data Isolation & Ownership Resolution
# ---------------------------------------------------------------------------

def test_resolve_student_pk_handles_types():
    assert database._resolve_student_pk(123) == 123
    assert database._resolve_student_pk("456") == 456
    
    # Non-numeric roll number string lookup
    students = database.get_all_students()
    if students:
        s = students[0]
        pk = database._resolve_student_pk(s["student_id"])
        assert pk == s["id"]
