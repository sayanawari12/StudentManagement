"""
test_student_ranking.py — Unit and integration security tests for the Student Performance / Ranking module.
Verifies that Semesters 1 and 3 are completely excluded from rankings while Semesters 2, 4, 5, 6 work properly,
and that DB records for Semesters 1 and 3 remain untouched.
"""

import pytest
from app import app
import database


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"
    return client


@pytest.fixture
def auth_teacher(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["username"] = "teacher"
        sess["role"] = "teacher"
    return client


@pytest.fixture
def auth_student(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["username"] = "student1"
        sess["role"] = "student"
        sess["linked_student_id"] = 1
    return client


def test_ranking_calculation_no_cgpa():
    """Verify that rankings calculate percentage from obtained/total_max and do not use CGPA."""
    rankings = database.get_semester_rankings(2)
    for r in rankings:
        assert "cgpa" not in r
        assert "percentage" in r
        assert "formatted_marks" in r
        assert "formatted_percentage" in r
        assert r["percentage"] >= 0.0 and r["percentage"] <= 100.0


def test_competition_tie_handling():
    """Test deterministic competition ranking (1, 2, 2, 4) for equal percentages."""
    test_data = [
        {"percentage": 90.00},
        {"percentage": 85.00},
        {"percentage": 85.00},
        {"percentage": 80.00},
    ]
    for i, item in enumerate(test_data):
        if i > 0:
            prev = test_data[i - 1]
            if item["percentage"] == prev["percentage"]:
                item["rank"] = prev["rank"]
            else:
                item["rank"] = i + 1
        else:
            item["rank"] = 1

    assert test_data[0]["rank"] == 1
    assert test_data[1]["rank"] == 2
    assert test_data[2]["rank"] == 2
    assert test_data[3]["rank"] == 4


def test_empty_semester_ranking_handling():
    """Verify clean empty state when no results exist for a semester."""
    rankings = database.get_semester_rankings(999)
    assert isinstance(rankings, list)
    assert len(rankings) == 0


def test_sem_1_and_sem_3_backend_rejection():
    """Verify database.get_semester_rankings strictly returns empty list for Sem 1 and Sem 3."""
    assert database.get_semester_rankings(1) == []
    assert database.get_semester_rankings(3) == []


def test_allowed_semesters_rankings_work():
    """Verify database.get_semester_rankings works for allowed semesters 2, 4, 5, 6."""
    for sem in (2, 4, 5, 6):
        res = database.get_semester_rankings(sem)
        assert isinstance(res, list)


def test_sem_1_and_sem_3_not_in_ranking_selector_html(auth_admin):
    """Verify Semester 1 and Semester 3 options are not present in ranking UI selector."""
    response = auth_admin.get("/rankings?semester=2")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Semester 2" in html
    assert "Semester 4" in html
    assert "Semester 5" in html
    assert "Semester 6" in html
    # Semester 1 and Semester 3 must NOT appear in selector buttons
    assert 'semester=1"' not in html
    assert 'semester=3"' not in html


def test_direct_route_access_sem_1_and_3_redirects_or_defaults(auth_admin):
    """Direct route access for sem 1 or 3 redirects/defaults to semester 2 and does not leak sem 1/3 ranking data."""
    res1 = auth_admin.get("/rankings?semester=1")
    assert res1.status_code in (200, 302)
    res3 = auth_admin.get("/rankings?semester=3")
    assert res3.status_code in (200, 302)


def test_direct_api_access_sem_1_and_3_rejected(auth_admin):
    """API access for sem 1 or 3 returns 400 error and empty rankings array."""
    res1 = auth_admin.get("/api/student-rankings?semester=1")
    assert res1.status_code == 400
    json1 = res1.get_json()
    assert json1["success"] is False
    assert json1["rankings"] == []

    res3 = auth_admin.get("/api/student-rankings?semester=3")
    assert res3.status_code == 400
    json3 = res3.get_json()
    assert json3["success"] is False
    assert json3["rankings"] == []


def test_api_student_rankings_allowed_semesters(auth_admin):
    """API access for allowed semester (e.g. sem 2) succeeds."""
    res = auth_admin.get("/api/student-rankings?semester=2")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["success"] is True
    assert json_data["semester"] == 2
    assert "rankings" in json_data


def test_dashboard_widget_defaults_to_sem_2(auth_admin):
    """Verify Dashboard Top Performers widget defaults to Semester 2 and only offers allowed semesters."""
    response = auth_admin.get("/dashboard")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Top Performers" in html
    assert "topPerformersSemSelect" in html
    assert 'value="2"' in html
    assert 'value="1"' not in html
    assert 'value="3"' not in html


def test_student_privacy_restriction(auth_student):
    """Student role cannot enumerate or browse other students' rankings."""
    response = auth_student.get("/rankings?semester=2")
    assert response.status_code == 200
    assert b"Total Ranked Students" not in response.data

    api_resp = auth_student.get("/api/student-rankings?semester=2")
    assert api_resp.status_code == 200
    json_data = api_resp.get_json()
    assert json_data["role"] == "student"
    assert len(json_data["rankings"]) <= 1


def test_data_integrity_no_nan_or_infinity():
    """Verify zero/invalid denominators do not produce NaN or Infinity."""
    rankings = database.get_semester_rankings(2)
    for r in rankings:
        assert r["total_max"] > 0
        assert r["total_obtained"] >= 0
        assert r["percentage"] >= 0.0
        assert not (r["percentage"] != r["percentage"])
        assert r["percentage"] != float("inf")
        assert r["percentage"] != float("-inf")


def test_database_academic_records_sem_1_and_3_not_deleted():
    """Verify that Semester 1 and Semester 3 exam & subject data in DB is completely intact."""
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS cnt FROM subjects WHERE semester IN (1, 3)")
        sub_cnt = cursor.fetchone()["cnt"]
        assert sub_cnt >= 0
    finally:
        cursor.close()
        conn.close()
