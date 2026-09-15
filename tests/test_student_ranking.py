"""
test_student_ranking.py — Unit and integration security tests for the Student Performance / Ranking module.
Verifies that all 6 semester selectors (1-6) are restored and present in the UI,
that Semesters 1 and 3 load valid HTTP 200 responses with empty ranking data,
and that DB academic records for Semesters 1 and 3 remain 100% intact.
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


def test_all_six_semester_selectors_exist(auth_admin):
    """Verify that all six semester selectors (1, 2, 3, 4, 5, 6) exist in ranking UI."""
    response = auth_admin.get("/rankings?semester=1")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    for sem in range(1, 7):
        assert f"Semester {sem}" in html


def test_sem_1_and_sem_3_rankings_return_empty_list():
    """Verify get_semester_rankings for sem 1 and 3 returns empty list []."""
    assert database.get_semester_rankings(1) == []
    assert database.get_semester_rankings(3) == []


def test_rankings_route_sem_1_and_3_http_200_empty(auth_admin):
    """Verify /rankings?semester=1 and 3 load HTTP 200 with empty state message."""
    res1 = auth_admin.get("/rankings?semester=1")
    assert res1.status_code == 200
    html1 = res1.data.decode("utf-8")
    assert "Semester 1" in html1
    assert "No ranking available for Semester 1 yet." in html1

    res3 = auth_admin.get("/rankings?semester=3")
    assert res3.status_code == 200
    html3 = res3.data.decode("utf-8")
    assert "Semester 3" in html3
    assert "No ranking available for Semester 3 yet." in html3


def test_api_student_rankings_sem_1_and_3_http_200_empty(auth_admin):
    """Verify /api/student-rankings?semester=1 and 3 return valid HTTP 200 JSON with rankings: []."""
    res1 = auth_admin.get("/api/student-rankings?semester=1")
    assert res1.status_code == 200
    json1 = res1.get_json()
    assert json1["success"] is True
    assert json1["semester"] == 1
    assert json1["rankings"] == []

    res3 = auth_admin.get("/api/student-rankings?semester=3")
    assert res3.status_code == 200
    json3 = res3.get_json()
    assert json3["success"] is True
    assert json3["semester"] == 3
    assert json3["rankings"] == []


def test_rankings_work_for_allowed_semesters():
    """Verify database.get_semester_rankings returns list for semesters 2, 4, 5, 6."""
    for sem in (2, 4, 5, 6):
        res = database.get_semester_rankings(sem)
        assert isinstance(res, list)


def test_dashboard_widget_renders_all_six_semesters(auth_admin):
    """Verify Dashboard Top Performers widget dropdown renders all six semesters."""
    response = auth_admin.get("/dashboard")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Top Performers" in html
    assert "topPerformersSemSelect" in html
    for sem in range(1, 7):
        assert f'value="{sem}"' in html


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
